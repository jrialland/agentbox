import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlmodel import SQLModel

import agentbox_models.tables  # noqa: F401


def _config(url: str) -> Config:
    config = Config("packages/agentbox-models/alembic.ini")
    config.set_main_option("script_location", "packages/agentbox-models/alembic")
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_plugin_migration_tolerates_tables_created_by_create_all(tmp_path):
    db = tmp_path / "drift.db"
    url = f"sqlite:///{db.as_posix()}"
    config = _config(url)

    command.upgrade(config, "cb4176fc9480")

    engine = sa.create_engine(url)
    SQLModel.metadata.create_all(engine)
    engine.dispose()

    command.upgrade(config, "head")

    engine = sa.create_engine(url)
    with engine.connect() as connection:
        revision = connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar()
        permissions = set(
            connection.execute(sa.text("SELECT name FROM permission")).scalars()
        )
        tables = set(sa.inspect(connection).get_table_names())
    engine.dispose()

    assert revision == "f1a2b3c4d5e6"
    assert {"plugins:read", "plugins:write"} <= permissions
    assert {"pluginstate", "agent_plugin_mcp_binding"} <= tables
