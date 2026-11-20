from agentbox_api.runtime import delete_session_data
from agentbox_api.subsessions import (
    cancel_sub_sessions,
    reconcile_running_sub_sessions,
)
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
                    sub_session_status="completed",
                    sub_session_depth=1,
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
                    sub_session_status="running",
                    sub_session_depth=1,
                )
            )
            await s.commit()
        await cancel_sub_sessions(factory, "parent")
        async with factory() as s:
            row = await s.get(SessionRow, "child")
        assert row.sub_session_status == "cancelled"

        async with factory() as s:
            row = await s.get(SessionRow, "child")
            row.sub_session_status = "running"
            s.add(row)
            await s.commit()
        await reconcile_running_sub_sessions(factory)
        async with factory() as s:
            row = await s.get(SessionRow, "child")
        assert row.sub_session_status == "failed"
        assert "interrupted" in (row.sub_session_error or "")
    finally:
        await engine.dispose()
