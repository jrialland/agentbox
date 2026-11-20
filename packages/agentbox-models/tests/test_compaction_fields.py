from sqlmodel import select

from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import Model, Provider, TurnRow


async def test_compaction_fields_roundtrip():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    try:
        async with factory() as s:
            s.add(Provider(id="p1", name="p", kind="test"))
            s.add(
                Model(
                    id="m1",
                    provider_id="p1",
                    name="m",
                    context_window=128_000,
                )
            )
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
