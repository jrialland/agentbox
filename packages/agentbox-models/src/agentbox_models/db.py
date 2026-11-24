"""Create the async database engine and initialize the schema.

The engine is created once per process from a resolved database URL. Shutdown
should call ``AsyncEngine.dispose`` on it; sessions obtained from the returned
factory own their own transactions and should be committed by the caller.
"""

from loguru import logger
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from agentbox_models.config import normalize_async_url


def create_engine_and_sessionmaker(database_url: str, echo: bool = False):
    """Create an async engine and a session factory for it.

    Every call builds independent objects, so callers should create one engine
    per process and reuse its session factory across requests.

    Args:
        database_url: SQLAlchemy URL. Synchronous spellings are normalized to
            async drivers first.
        echo: When true, log every SQL statement emitted by the engine.

    Returns:
        A ``(engine, session_factory)`` tuple. The factory disables attribute
        expiry on commit so ORM objects remain usable after commit.
    """
    database_url = normalize_async_url(database_url)
    # ``pool_pre_ping`` drops stale pooled connections, which matters for
    # long-lived server-side databases that may close idle connections.
    engine = create_async_engine(database_url, echo=echo, pool_pre_ping=True)
    if database_url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _record):
            # SQLite enforces foreign keys only when enabled per connection, so
            # turn on the pragma for every new connection to match other vendors.
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    # ``expire_on_commit=False`` avoids implicit reloads after commit, keeping
    # objects usable outside the transaction.
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


async def init_db(engine: AsyncEngine) -> None:
    """Create any missing tables for the SQLModel metadata.

    This uses ``create_all``, which only creates absent tables and never alters
    existing ones; schema changes require an Alembic migration. Run it once at
    startup rather than concurrently with other schema work.

    Args:
        engine: Engine whose database should be initialized.
    """
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.debug("database initialized")
