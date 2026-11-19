from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import Agent, Model, Provider


async def test_agent_avatar_columns_roundtrip():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(Provider(id="p", name="t", kind="generic"))
        s.add(Model(id="m", provider_id="p", name="mm"))
        s.add(
            Agent(
                id="a",
                name="a",
                description="",
                instructions="",
                model_id="m",
                avatar_data=b"\x89PNG",
                avatar_media_type="image/png",
            )
        )
        await s.commit()
    async with factory() as s:
        a = await s.get(Agent, "a")
        assert a.avatar_data == b"\x89PNG"
        assert a.avatar_media_type == "image/png"
    await engine.dispose()
