from sqlmodel import select

import agentbox_models.tables.auth  # noqa: F401  (registers User in metadata)
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import User
from agentbox_models.tables.core import (
    Agent,
    Model,
    Project,
    Provider,
    SessionRow,
    TurnRow,
)


async def test_agent_and_turn_roundtrip():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="u", email="u@x", password_hash="h"))
        s.add(
            Provider(
                id="prov1",
                name="openai",
                kind="openai_responses",
                base_url="https://api.openai.com/v1",
            )
        )
        await s.flush()
        s.add(Model(id="m1", provider_id="prov1", name="gpt-4o"))
        await s.flush()
        s.add(
            Agent(
                id="a1",
                name="coder",
                description="d",
                instructions="i",
                model_id="m1",
            )
        )
        s.add(Project(id="pr1", name="p", path=".", owner_id="u1"))
        await s.flush()
        s.add(SessionRow(id="s1", project_id="pr1", agent_id="a1"))
        await s.flush()
        s.add(TurnRow(id="t1", session_id="s1", role="user", content="hi", parent_id=None))
        await s.commit()
        agent = (await s.execute(select(Agent).where(Agent.id == "a1"))).scalars().first()
        assert agent is not None
        assert agent.model_id == "m1"
        turns = (
            await s.execute(select(TurnRow).where(TurnRow.session_id == "s1"))
        ).scalars().all()
        assert len(turns) == 1
    await engine.dispose()
