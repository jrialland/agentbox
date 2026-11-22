from sqlmodel import select

from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import User
from agentbox_models.tables.core import (
    Agent,
    Model,
    Project,
    Provider,
    SessionRow,
)


async def test_subagent_session_fields_roundtrip():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    try:
        async with factory() as s:
            s.add(User(id="u1", username="u", email="u@x", password_hash="h"))
            s.add(Provider(id="p1", name="test", kind="test"))
            await s.flush()
            s.add(Model(id="m1", provider_id="p1", name="test"))
            await s.flush()
            s.add(Agent(id="a", name="a", description="", instructions="", model_id="m1"))
            s.add(Agent(id="b", name="b", description="", instructions="", model_id="m1"))
            s.add(Project(id="p", name="p", path=".", owner_id="u1"))
            await s.flush()
            s.add(SessionRow(id="parent", project_id="p", agent_id="a"))
            await s.flush()
            s.add(
                SessionRow(
                    id="child",
                    project_id="p",
                    agent_id="b",
                    parent_session_id="parent",
                    subagent_session_status="running",
                    subagent_session_error=None,
                    subagent_session_depth=1,
                )
            )
            await s.commit()
        async with factory() as s:
            child = (
                await s.execute(select(SessionRow).where(SessionRow.id == "child"))
            ).scalars().first()
        assert child is not None
        assert child.parent_session_id == "parent"
        assert child.subagent_session_status == "running"
        assert child.subagent_session_depth == 1
    finally:
        await engine.dispose()
