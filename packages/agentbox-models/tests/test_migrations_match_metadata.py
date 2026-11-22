import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlmodel import SQLModel

import agentbox_models.tables  # noqa: F401


def test_initial_migration_matches_metadata(tmp_path):
    db = tmp_path / "match.db"
    config = Config("packages/agentbox-models/alembic.ini")
    config.set_main_option("script_location", "packages/agentbox-models/alembic")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db.as_posix()}")
    command.upgrade(config, "head")

    engine = sa.create_engine(f"sqlite:///{db.as_posix()}")
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, SQLModel.metadata) == []
    engine.dispose()
