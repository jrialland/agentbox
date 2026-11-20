import asyncio

from sqlmodel import select

from agentbox_api.skills import prepare_agent
from agentbox_api.subsessions import ApiSubSessionRunner, SubSessionContext
from agentbox_harness.compaction import CompactionConfig
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import Agent, Model, Project, Provider, SessionRow


async def _setup(tmp_path):
    db = tmp_path / "subsessions.db"
    engine, factory = create_engine_and_sessionmaker(
        f"sqlite+aiosqlite:///{db.as_posix()}"
    )
    await init_db(engine)
    async with factory() as s:
        s.add(Provider(id="prov", name="prov", kind="test"))
        s.add(Model(id="m1", provider_id="prov", name="test-model"))
        s.add(
            Agent(
                id="parent-agent",
                name="parent",
                description="d",
                instructions="i",
                model_id="m1",
                sub_agent_ids='["child"]',
            )
        )
        s.add(
            Agent(
                id="child-agent",
                name="child",
                description="d",
                instructions="i",
                model_id="m1",
            )
        )
        s.add(Project(id="p1", name="p", path=str(tmp_path), owner_id="u1"))
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
    return SubSessionContext(
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


async def _prepared(factory, tmp_path):
    return await prepare_agent(
        factory,
        "parent",
        str(tmp_path),
        str(tmp_path / "skills"),
        session_id="parent-session",
    )


async def test_background_child_completes_and_reports_output(tmp_path):
    engine, factory = await _setup(tmp_path)
    try:
        prepared = await _prepared(factory, tmp_path)
        runner = ApiSubSessionRunner(_context(factory, tmp_path))
        started = await runner.start(
            "parent-session", prepared.spec, "child", "do work", wait=False
        )
        assert "Started sub-session" in started
        child_id = started.split()[2]
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
        prepared = await _prepared(factory, tmp_path)
        runner = ApiSubSessionRunner(_context(factory, tmp_path))
        output = await runner.start(
            "parent-session", prepared.spec, "child", "do work", wait=True
        )
        assert "completed" in output
        assert "Hello from the test provider" in output
    finally:
        await engine.dispose()


async def test_unknown_agent_empty_task_and_depth_limit(tmp_path):
    engine, factory = await _setup(tmp_path)
    try:
        prepared = await _prepared(factory, tmp_path)
        runner = ApiSubSessionRunner(_context(factory, tmp_path, depth=3))
        assert "maximum depth" in await runner.start(
            "parent-session", prepared.spec, "child", "x", False
        )
        shallow = ApiSubSessionRunner(_context(factory, tmp_path))
        assert "unknown agent" in await shallow.start(
            "parent-session", prepared.spec, "missing", "x", False
        )
        assert "must not be empty" in await shallow.start(
            "parent-session", prepared.spec, "child", "  ", False
        )
    finally:
        await engine.dispose()


async def test_child_agent_spec_gets_own_session_and_turns(tmp_path):
    engine, factory = await _setup(tmp_path)
    try:
        prepared = await _prepared(factory, tmp_path)
        runner = ApiSubSessionRunner(_context(factory, tmp_path))
        result = await runner.start(
            "parent-session", prepared.spec, "child", "work", wait=True
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
