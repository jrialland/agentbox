import asyncio

from sqlmodel import select

from agentbox_api.subagent_sessions import (
    ApiSubagentSessionRunner,
    SubagentSessionContext,
)
from agentbox_harness.compaction import CompactionConfig
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import User
from agentbox_models.tables.core import Agent, Model, Project, Provider, SessionRow


async def _setup(tmp_path):
    db = tmp_path / "subagent_sessions.db"
    engine, factory = create_engine_and_sessionmaker(
        f"sqlite+aiosqlite:///{db.as_posix()}"
    )
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="u", email="u@x", password_hash="h"))
        s.add(Provider(id="prov", name="prov", kind="test"))
        await s.flush()
        s.add(Model(id="m1", provider_id="prov", name="test-model"))
        await s.flush()
        s.add(
            Agent(
                id="parent-agent",
                name="parent",
                description="d",
                instructions="i",
                model_id="m1",
            )
        )
        await s.flush()
        s.add(
            Agent(
                id="child-agent",
                name="child",
                description="d",
                instructions="i",
                model_id="m1",
            )
        )
        await s.flush()
        s.add(Project(id="p1", name="p", path=str(tmp_path), owner_id="u1"))
        await s.flush()
        s.add(
            SessionRow(
                id="parent-session",
                project_id="p1",
                agent_id="parent-agent",
            )
        )
        await s.commit()
    return engine, factory


async def _slow_setup(tmp_path):
    db = tmp_path / "slow.db"
    engine, factory = create_engine_and_sessionmaker(
        f"sqlite+aiosqlite:///{db.as_posix()}"
    )
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="u", email="u@x", password_hash="h"))
        s.add(Provider(id="slow-prov", name="slow", kind="test_slow"))
        await s.flush()
        s.add(Model(id="slow-model", provider_id="slow-prov", name="slow-model"))
        await s.flush()
        s.add(
            Agent(
                id="parent-agent",
                name="parent",
                description="d",
                instructions="i",
                model_id="slow-model",
            )
        )
        await s.flush()
        s.add(
            Agent(
                id="slow-child-agent",
                name="slow-child",
                description="d",
                instructions="i",
                model_id="slow-model",
            )
        )
        await s.flush()
        s.add(Project(id="p1", name="p", path=str(tmp_path), owner_id="u1"))
        await s.flush()
        s.add(
            SessionRow(
                id="parent-session",
                project_id="p1",
                agent_id="parent-agent",
            )
        )
        await s.commit()
    return engine, factory


def _context(factory, tmp_path, depth=0):
    return SubagentSessionContext(
        factory=factory,
        project_root=str(tmp_path),
        skills_user_dir=str(tmp_path / "skills"),
        extra_roots=[],
        web_config=None,
        compaction=CompactionConfig(),
        media_max_dimension=1568,
        media_max_bytes=1_500_000,
        depth=depth,
    )


async def test_list_agents_includes_all_agents(tmp_path):
    engine, factory = await _setup(tmp_path)
    try:
        runner = ApiSubagentSessionRunner(_context(factory, tmp_path))
        listed = await runner.list_agents()
        assert "- child:" in listed
        assert "- parent:" in listed
    finally:
        await engine.dispose()


async def test_get_and_cancel_require_parent_ownership(tmp_path):
    engine, factory = await _setup(tmp_path)
    try:
        runner = ApiSubagentSessionRunner(_context(factory, tmp_path))
        assert (
            await runner.get("other-parent", "missing", 100)
            == "Subagent session not found."
        )
        assert (
            await runner.cancel("other-parent", "missing")
            == "Subagent session not found."
        )
    finally:
        await engine.dispose()


async def test_background_child_completes_and_reports_output(tmp_path):
    engine, factory = await _setup(tmp_path)
    try:
        runner = ApiSubagentSessionRunner(_context(factory, tmp_path))
        started = await runner.start(
            "parent-session", "child", "do work", wait=False
        )
        assert "Started subagent session" in started
        child_id = started.split()[3]
        output = ""
        for _ in range(50):
            output = await runner.get("parent-session", child_id, 4000)
            if "completed" in output:
                break
            await asyncio.sleep(0.1)
        assert "completed" in output
        assert "Hello from the test provider" in output
        assert "child" in await runner.list("parent-session")
    finally:
        await engine.dispose()


async def test_wait_true_returns_output(tmp_path):
    engine, factory = await _setup(tmp_path)
    try:
        runner = ApiSubagentSessionRunner(_context(factory, tmp_path))
        output = await runner.start(
            "parent-session", "child", "do work", wait=True
        )
        assert "completed" in output
        assert "Hello from the test provider" in output
    finally:
        await engine.dispose()


async def test_unknown_agent_empty_task_and_depth_limit(tmp_path):
    engine, factory = await _setup(tmp_path)
    try:
        runner = ApiSubagentSessionRunner(_context(factory, tmp_path, depth=3))
        assert "maximum depth" in await runner.start(
            "parent-session", "child", "x", False
        )
        shallow = ApiSubagentSessionRunner(_context(factory, tmp_path))
        assert "unknown agent" in await shallow.start(
            "parent-session", "missing", "x", False
        )
        assert "must not be empty" in await shallow.start(
            "parent-session", "child", "  ", False
        )
    finally:
        await engine.dispose()


async def test_child_agent_spec_gets_own_session_and_turns(tmp_path):
    engine, factory = await _setup(tmp_path)
    try:
        runner = ApiSubagentSessionRunner(_context(factory, tmp_path))
        result = await runner.start(
            "parent-session", "child", "work", wait=True
        )
        assert "child" in result
        async with factory() as s:
            children = (
                await s.execute(
                    select(SessionRow).where(
                        SessionRow.parent_session_id == "parent-session"
                    )
                )
            ).scalars().all()
        assert len(children) == 1
    finally:
        await engine.dispose()


async def test_parallel_subagent_sessions_live_output_and_wait(tmp_path):
    engine, factory = await _slow_setup(tmp_path)
    try:
        runner = ApiSubagentSessionRunner(_context(factory, tmp_path))
        first = await runner.start(
            "parent-session", "slow-child", "first task", wait=False
        )
        second = await runner.start(
            "parent-session", "slow-child", "second task", wait=False
        )
        first_id = first.split()[3]
        second_id = second.split()[3]

        await asyncio.sleep(0.9)
        first_output = await runner.get("parent-session", first_id, 4000)
        assert "running" in first_output
        assert "Partial" in first_output

        any_result = await runner.wait_many(
            "parent-session", [first_id, second_id], "any", 6
        )
        assert "completed" in any_result or "failed" in any_result

        all_result = await runner.wait_many(
            "parent-session", [first_id, second_id], "all", 10
        )
        assert "Partial answer still running" in all_result
    finally:
        await engine.dispose()
