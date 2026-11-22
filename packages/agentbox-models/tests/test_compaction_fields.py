from sqlmodel import select

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


async def test_compaction_fields_roundtrip():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    try:
        async with factory() as s:
            s.add(User(id="u1", username="u", email="u@x", password_hash="h"))
            s.add(Provider(id="p1", name="p", kind="test"))
            await s.flush()
            s.add(
                Model(
                    id="m1",
                    provider_id="p1",
                    name="m",
                    context_window=128_000,
                )
            )
            await s.flush()
            s.add(Agent(id="a1", name="a", description="", instructions="", model_id="m1"))
            s.add(Project(id="pr1", name="p", path=".", owner_id="u1"))
            await s.flush()
            s.add(SessionRow(id="s1", project_id="pr1", agent_id="a1"))
            s.add(
                TurnRow(
                    id="t1",
                    session_id="s1",
                    role="assistant",
                    content="x",
                    context_tokens=42,
                )
            )
            await s.commit()
        async with factory() as s:
            model = (
                await s.execute(select(Model).where(Model.id == "m1"))
            ).scalars().first()
            turn = (
                await s.execute(select(TurnRow).where(TurnRow.id == "t1"))
            ).scalars().first()
        assert model is not None and model.context_window == 128_000
        assert turn is not None and turn.context_tokens == 42
    finally:
        await engine.dispose()
