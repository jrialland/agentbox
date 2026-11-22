from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import Agent, MediaFile, Model, Provider


async def test_agent_avatar_columns_roundtrip():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(Provider(id="p", name="t", kind="generic"))
        await s.flush()
        s.add(Model(id="m", provider_id="p", name="mm"))
        s.add(
            MediaFile(
                id="f",
                storage_path="avatars/f.png",
                media_type="image/png",
                size_bytes=4,
                sha256="0" * 64,
            )
        )
        await s.flush()
        s.add(
            Agent(
                id="a",
                name="a",
                description="",
                instructions="",
                model_id="m",
                avatar_file_id="f",
            )
        )
        await s.commit()
    async with factory() as s:
        a = await s.get(Agent, "a")
        assert a.avatar_file_id == "f"
        media = await s.get(MediaFile, "f")
        assert media is not None
        assert media.media_type == "image/png"
    await engine.dispose()
