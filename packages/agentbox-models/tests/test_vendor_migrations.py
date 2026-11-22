import asyncio

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel


def _config(url: str) -> Config:
    config = Config("packages/agentbox-models/alembic.ini")
    config.set_main_option("script_location", "packages/agentbox-models/alembic")
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.mark.parametrize("vendor", ["postgresql", "mysql", "mariadb"])
@pytest.mark.timeout(180)
def test_migrations_on_container_vendor(request, vendor):
    name = "postgres_url" if vendor == "postgresql" else f"{vendor}_url"
    url = request.getfixturevalue(name)
    config = _config(url)

    async def reset():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
        await engine.dispose()

    asyncio.run(reset())
    command.upgrade(config, "head")
    command.downgrade(config, "base")
