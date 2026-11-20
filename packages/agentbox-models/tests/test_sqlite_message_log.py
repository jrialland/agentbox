from agentbox_harness.session import Turn
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.repos.message_log import SQLiteMessageLogStore


async def test_message_log_roundtrip():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    store = SQLiteMessageLogStore(factory, "sess1")
    await store.append(Turn(id="t1", role="user", content="hello", parent_id=None))
    await store.append(Turn(id="t2", role="assistant", content="hi", parent_id="t1"))
    turns = await store.list_turns()
    assert {t.id for t in turns} == {"t1", "t2"}
    got = await store.get("t2")
    assert got.role == "assistant"
    assert got.parent_id == "t1"
    await engine.dispose()


async def test_message_log_roundtrips_activity_and_attachments():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    store = SQLiteMessageLogStore(factory, "sess1")
    await store.append(
        Turn(
            id="t1",
            role="user",
            content="hello",
            parent_id=None,
            attachments=[{"id": "a1", "filename": "note.txt", "media_type": "text/plain"}],
        )
    )
    await store.append(
        Turn(
            id="t2",
            role="assistant",
            content="hi",
            parent_id="t1",
            activity={
                "status": "success",
                "reasoning_ms": 1200,
                "tools": [{"name": "read_text_file", "status": "success", "duration_ms": 10}],
            },
        )
    )
    user = await store.get("t1")
    assistant = await store.get("t2")
    assert user.attachments == [
        {"id": "a1", "filename": "note.txt", "media_type": "text/plain"}
    ]
    assert assistant.activity == {
        "status": "success",
        "reasoning_ms": 1200,
        "tools": [{"name": "read_text_file", "status": "success", "duration_ms": 10}],
    }
    await engine.dispose()
