import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def _config(db) -> Config:
    config = Config("packages/agentbox-models/alembic.ini")
    config.set_main_option("script_location", "packages/agentbox-models/alembic")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db.as_posix()}")
    return config


def test_initial_schema_upgrade_and_downgrade(tmp_path):
    db = tmp_path / "mig.db"
    config = _config(db)
    command.upgrade(config, "head")

    engine = sa.create_engine(f"sqlite:///{db.as_posix()}")
    inspector = sa.inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "agent",
        "agent_card",
        "agent_mode",
        "agent_mode_flag",
        "agent_tool_binding",
        "apikey",
        "apikey_scope",
        "media_file",
        "project",
        "project_root",
        "session_attachment",
        "sessionrow",
        "turn_activity",
        "turn_attachment",
        "turn_tool_activity",
        "turnrow",
    } <= tables
    engine.dispose()

    command.downgrade(config, "base")
    engine = sa.create_engine(f"sqlite:///{db.as_posix()}")
    remaining = set(sa.inspect(engine).get_table_names())
    assert remaining <= {"alembic_version"}
    engine.dispose()
