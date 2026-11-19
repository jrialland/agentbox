import base64

from acp import schema as s

from agentbox_api.acp_server import prompt_parts


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def test_prompt_parts_text_and_link():
    parts = prompt_parts([
        s.TextContentBlock(text="hello"),
        s.ResourceContentBlock(uri="file:///x.py", name="x.py", mime_type="text/x-python"),
    ])
    assert parts[0] == "hello"
    assert "x.py" in parts[1]


def test_prompt_parts_image_and_audio():
    parts = prompt_parts([
        s.ImageContentBlock(data=_b64(b"img"), mime_type="image/png"),
        s.AudioContentBlock(data=_b64(b"aud"), mime_type="audio/wav"),
    ])
    assert parts[0].media_type == "image/png"
    assert parts[1].media_type == "audio/wav"


def test_prompt_parts_embedded_text():
    parts = prompt_parts([
        s.EmbeddedResourceContentBlock(
            resource={"uri": "file:///a.txt", "text": "hi", "mimeType": "text/plain"}
        )
    ])
    assert "hi" in parts[0]


def test_text_delta_maps_to_agent_message_chunk():
    from pydantic_ai.messages import PartDeltaEvent, TextPartDelta

    from agentbox_api.acp_server import update_for_event

    upd = update_for_event(PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="hi")))
    assert upd.session_update == "agent_message_chunk"
    assert upd.content.text == "hi"


def test_tool_call_start_and_result():
    from pydantic_ai.messages import (
        FunctionToolCallEvent,
        FunctionToolResultEvent,
        ToolCallPart,
        ToolReturnPart,
    )

    from agentbox_api.acp_server import update_for_event

    call = FunctionToolCallEvent(
        part=ToolCallPart(tool_name="read_text_file", args={}, tool_call_id="c1")
    )
    start = update_for_event(call)
    assert start.session_update == "tool_call"
    assert start.tool_call_id == "c1"
    done = update_for_event(
        FunctionToolResultEvent(
            part=ToolReturnPart(tool_name="read_text_file", content="ok", tool_call_id="c1")
        )
    )
    assert done.session_update == "tool_call_update"
    assert done.status == "completed"


class _FakeConn:
    def __init__(self):
        self.updates = []

    async def session_update(self, session_id, update, **kwargs):
        self.updates.append(update)


async def _seed_acp(factory):
    from agentbox_api.security import hash_password
    from agentbox_models.tables.auth import User
    from agentbox_models.tables.core import Agent, Model, Provider

    async with factory() as db:
        db.add(Provider(id="p", name="test", kind="test"))
        db.add(Model(id="m", provider_id="p", name="test-model"))
        db.add(
            Agent(
                id="ag",
                name="acp-test",
                description="",
                instructions="",
                model_id="m",
                tool_bindings="[]",
                mode_definitions='[{"name":"ask","flags":{"write":false}},{"name":"agent","flags":{"write":true}}]',
                sub_agent_ids="[]",
            )
        )
        db.add(
            User(
                id="admin1",
                username="admin",
                email="a@x",
                password_hash=hash_password("pw"),
            )
        )
        await db.commit()


async def test_acp_lifecycle(tmp_path):
    from agentbox_api.acp_server import AgentboxAcpAgent
    from agentbox_models.db import create_engine_and_sessionmaker, init_db

    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    await _seed_acp(factory)
    try:
        from agentbox_api.config import Settings

        agent = AgentboxAcpAgent(
            "acp-test",
            factory,
            Settings(jwt_secret="s" * 32, skills_user_dir=str(tmp_path / "skills")),
        )
        conn = _FakeConn()
        agent.on_connect(conn)  # ty: ignore[invalid-argument-type]

        init = await agent.initialize(1)
        assert init.agent_capabilities.prompt_capabilities.image is True

        created = await agent.new_session(cwd=str(tmp_path), mcp_servers=[])
        sid = created.session_id
        assert {m.id for m in created.modes.available_modes} == {"ask", "agent"}

        resp = await agent.prompt(sid, [s.TextContentBlock(text="hi")])
        assert resp.stop_reason == "end_turn"
        text = "".join(
            u.content.text
            for u in conn.updates
            if getattr(u, "session_update", None) == "agent_message_chunk"
        )
        assert "Hello from the test provider" in text

        listed = await agent.list_sessions(cwd=str(tmp_path))
        assert any(x.session_id == sid for x in listed.sessions)

        conn.updates.clear()
        await agent.load_session(str(tmp_path), sid, mcp_servers=[])
        assert any(
            getattr(u, "session_update", None)
            in ("user_message_chunk", "agent_message_chunk")
            for u in conn.updates
        )

        await agent.delete_session(sid)
        listed2 = await agent.list_sessions(cwd=str(tmp_path))
        assert all(x.session_id != sid for x in listed2.sessions)
    finally:
        await engine.dispose()

