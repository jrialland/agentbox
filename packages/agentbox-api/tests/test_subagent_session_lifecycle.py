from agentbox_api.runtime import delete_session_data
from agentbox_api.subagent_sessions import (
    ApiSubagentSessionRunner,
    SubagentSessionContext,
    SubagentSessionJob,
    SubagentSessionManager,
    cancel_subagent_sessions,
    reconcile_running_subagent_sessions,
)
from agentbox_harness.compaction import CompactionConfig
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import SessionRow


async def test_parent_delete_removes_children(tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    try:
        async with factory() as s:
            s.add(SessionRow(id="parent", project_id="p", agent_id="a"))
            s.add(
                SessionRow(
                    id="child",
                    project_id="p",
                    agent_id="b",
                    parent_session_id="parent",
                    subagent_session_status="completed",
                    subagent_session_depth=1,
                )
            )
            await s.commit()
        await delete_session_data(factory, "parent")
        async with factory() as s:
            assert await s.get(SessionRow, "parent") is None
            assert await s.get(SessionRow, "child") is None
    finally:
        await engine.dispose()


async def test_cancel_and_reconcile_running_children(tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    try:
        async with factory() as s:
            s.add(
                SessionRow(
                    id="child",
                    project_id="p",
                    agent_id="b",
                    parent_session_id="parent",
                    subagent_session_status="running",
                    subagent_session_depth=1,
                )
            )
            await s.commit()
        await cancel_subagent_sessions(factory, "parent")
        async with factory() as s:
            row = await s.get(SessionRow, "child")
        assert row.subagent_session_status == "cancelled"

        async with factory() as s:
            row = await s.get(SessionRow, "child")
            row.subagent_session_status = "running"
            s.add(row)
            await s.commit()
        await reconcile_running_subagent_sessions(factory)
        async with factory() as s:
            row = await s.get(SessionRow, "child")
        assert row.subagent_session_status == "failed"
        assert "interrupted" in (row.subagent_session_error or "")
    finally:
        await engine.dispose()


async def test_cancel_recurses_through_grandchildren(tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    try:
        async with factory() as s:
            s.add(SessionRow(id="parent", project_id="p", agent_id="a"))
            s.add(
                SessionRow(
                    id="child",
                    project_id="p",
                    agent_id="b",
                    parent_session_id="parent",
                    subagent_session_status="running",
                    subagent_session_depth=1,
                )
            )
            s.add(
                SessionRow(
                    id="grandchild",
                    project_id="p",
                    agent_id="c",
                    parent_session_id="child",
                    subagent_session_status="running",
                    subagent_session_depth=2,
                )
            )
            await s.commit()

        runner = ApiSubagentSessionRunner(
            SubagentSessionContext(
                factory=factory,
                project_root=str(tmp_path),
                skills_user_dir=str(tmp_path / "skills"),
                extra_roots=[],
                web_config=None,
                compaction=CompactionConfig(),
                media_max_dimension=1568,
                media_max_bytes=1_500_000,
                depth=0,
            )
        )
        result = await runner.cancel("parent", "child")
        assert result == "Cancelled subagent session child."
        async with factory() as s:
            child = await s.get(SessionRow, "child")
            grandchild = await s.get(SessionRow, "grandchild")
        assert child.subagent_session_status == "cancelled"
        assert grandchild.subagent_session_status == "cancelled"
    finally:
        await engine.dispose()


async def test_manager_cancel_recurses_live_jobs():
    manager = SubagentSessionManager()
    child = SubagentSessionJob("child", "parent", "sub", "task", 1)
    grandchild = SubagentSessionJob("grandchild", "child", "sub", "task", 2)
    manager.register(child)
    manager.register(grandchild)

    manager.cancel("child")
    assert child.status == "cancelled"
    assert grandchild.status == "cancelled"
    assert child.done.is_set()
    assert grandchild.done.is_set()
