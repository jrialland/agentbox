from sqlmodel import Field, SQLModel, select

from agentbox_models.db import create_engine_and_sessionmaker, init_db


class Probe(SQLModel, table=True):
    id: str = Field(primary_key=True)
    value: str


async def test_create_tables_and_insert():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as session:
        session.add(Probe(id="p1", value="hello"))
        await session.commit()
        result = await session.execute(select(Probe).where(Probe.id == "p1"))
        row = result.scalars().first()
        assert row.value == "hello"
    await engine.dispose()

async def test_engine_factory_normalizes_sync_url(tmp_path):
    db = tmp_path / "sync.db"
    engine, factory = create_engine_and_sessionmaker(f"sqlite:///{db.as_posix()}")
    assert engine.url.drivername == "sqlite+aiosqlite"
    await engine.dispose()


async def test_engine_factory_keeps_async_url(tmp_path):
    engine, _ = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    assert engine.url.drivername == "sqlite+aiosqlite"
    await engine.dispose()
