import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def _config(db) -> Config:
    config = Config("packages/agentbox-models/alembic.ini")
    config.set_main_option("script_location", "packages/agentbox-models/alembic")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db.as_posix()}")
    return config


def test_migration_drops_and_renames(tmp_path):
    db = tmp_path / "mig.db"
    config = _config(db)
    command.upgrade(config, "e5f6a7b8c9d0")

    engine = sa.create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO agent "
                "(id, name, description, instructions, model_id, tool_bindings, "
                "mode_definitions, sub_agent_ids, created_at) "
                "VALUES ('a1', 'a', 'd', 'i', 'm1', '[]', '[]', '[\"x\"]', "
                "'2026-01-01 00:00:00')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO sessionrow "
                "(id, project_id, agent_id, sub_session_status, sub_session_depth, "
                "created_at) VALUES ('s1', 'p', 'a1', 'running', 1, "
                "'2026-01-01 00:00:00')"
            )
        )

    command.upgrade(config, "head")

    inspector = sa.inspect(engine)
    agent_columns = {column["name"] for column in inspector.get_columns("agent")}
    session_columns = {
        column["name"] for column in inspector.get_columns("sessionrow")
    }
    assert "sub_agent_ids" not in agent_columns
    assert "subagent_session_status" in session_columns
    assert "sub_session_status" not in session_columns
    with engine.connect() as conn:
        value = conn.execute(
            sa.text(
                "SELECT subagent_session_status FROM sessionrow WHERE id = 's1'"
            )
        ).scalar_one()
    assert value == "running"

    command.downgrade(config, "e5f6a7b8c9d0")
    inspector = sa.inspect(engine)
    assert "sub_agent_ids" in {c["name"] for c in inspector.get_columns("agent")}
    assert "sub_session_status" in {
        c["name"] for c in inspector.get_columns("sessionrow")
    }
    engine.dispose()
