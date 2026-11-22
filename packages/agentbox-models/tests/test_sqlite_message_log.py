from agentbox_harness.session import Turn
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.repos.message_log import DatabaseMessageLogStore
from agentbox_models.tables.auth import User
from agentbox_models.tables.core import (
    Agent,
    MediaFile,
    Model,
    Project,
    Provider,
    SessionAttachment,
    SessionRow,
)


async def _seed(factory):
    async with factory() as s:
        s.add(User(id="u1", username="a", email="a@x", password_hash="h"))
        s.add(Provider(id="p1", name="test", kind="generic"))
        await s.flush()
        s.add(Model(id="m1", provider_id="p1", name="test-model"))
        await s.flush()
        s.add(
            Agent(
                id="a1",
                name="bot",
                description="",
                instructions="",
                model_id="m1",
            )
        )
        s.add(Project(id="pr1", name="p", path="/tmp/p", owner_id="u1"))
        await s.flush()
        s.add(SessionRow(id="s1", project_id="pr1", agent_id="a1"))
        s.add(
            MediaFile(
                id="f1",
                storage_path="attachments/f1.txt",
                media_type="text/plain",
                size_bytes=5,
                sha256="0" * 64,
            )
        )
        await s.flush()
        s.add(
            SessionAttachment(
                id="at1", session_id="s1", file_id="f1", filename="note.txt"
            )
        )
        await s.commit()


async def test_message_log_roundtrip():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    await _seed(factory)
    store = DatabaseMessageLogStore(factory, "s1")
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
    await _seed(factory)
    store = DatabaseMessageLogStore(factory, "s1")
    await store.append(
        Turn(
            id="t1",
            role="user",
            content="hello",
            parent_id=None,
            attachments=[
                {"id": "at1", "filename": "note.txt", "media_type": "text/plain"}
            ],
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
                "reasoning_text": "thinking",
                "tools": [
                    {
                        "name": "read_text_file",
                        "status": "success",
                        "duration_ms": 10,
                        "args": "{}",
                        "result": "ok",
                    }
                ],
            },
        )
    )
    user = await store.get("t1")
    assistant = await store.get("t2")
    assert user.attachments == [
        {"id": "at1", "filename": "note.txt", "media_type": "text/plain"}
    ]
    assert assistant.activity is not None
    assert assistant.activity["reasoning_text"] == "thinking"
    assert assistant.activity["tools"][0]["result"] == "ok"
    await engine.dispose()
