import pytest
from sqlalchemy import JSON, LargeBinary, Text
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel

import agentbox_models.tables  # noqa: F401
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import SessionRow


def test_no_json_or_binary_columns():
    for table in SQLModel.metadata.tables.values():
        for column in table.columns:
            assert not isinstance(column.type, (JSON, LargeBinary)), (
                f"{table.name}.{column.name} must not use JSON or LargeBinary"
            )


def test_new_tables_exist():
    names = set(SQLModel.metadata.tables)
    assert {
        "media_file",
        "agent_tool_binding",
        "agent_tool_binding_required_flag",
        "agent_tool_binding_arg",
        "agent_tool_binding_env",
        "agent_tool_binding_env_passthrough",
        "agent_mode",
        "agent_mode_flag",
        "project_root",
        "turn_activity",
        "turn_tool_activity",
        "turn_attachment",
        "apikey_scope",
    } <= names


def test_long_text_columns_use_text():
    expected = {
        ("agent", "description"),
        ("agent", "instructions"),
        ("turnrow", "content"),
        ("turn_activity", "reasoning_text"),
        ("turn_tool_activity", "args"),
        ("turn_tool_activity", "result"),
    }
    for table_name, column_name in expected:
        column = SQLModel.metadata.tables[table_name].columns[column_name]
        assert isinstance(column.type, Text), f"{table_name}.{column_name} must be Text"


def test_removed_columns_are_gone():
    assert "tool_bindings" not in SQLModel.metadata.tables["agent"].columns
    assert "mode_definitions" not in SQLModel.metadata.tables["agent"].columns
    assert "avatar_data" not in SQLModel.metadata.tables["agent"].columns
    assert "extra_roots" not in SQLModel.metadata.tables["project"].columns
    assert "head_turn_id" not in SQLModel.metadata.tables["sessionrow"].columns
    assert "activity" not in SQLModel.metadata.tables["turnrow"].columns
    assert "attachments" not in SQLModel.metadata.tables["turnrow"].columns
    assert "data" not in SQLModel.metadata.tables["session_attachment"].columns
    assert "scopes" not in SQLModel.metadata.tables["apikey"].columns

async def test_sqlite_enforces_foreign_keys():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    with pytest.raises(IntegrityError):
        async with factory() as s:
            s.add(SessionRow(id="s1", project_id="missing", agent_id="missing"))
            await s.commit()
    await engine.dispose()
