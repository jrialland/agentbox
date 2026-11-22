from loguru import logger
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel


def create_engine_and_sessionmaker(database_url: str, echo: bool = False):
    engine = create_async_engine(database_url, echo=echo)
    if database_url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.debug("database initialized")
