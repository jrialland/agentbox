import os
import sys

from acp import PROTOCOL_VERSION, Client, spawn_agent_process
from acp import schema as s

from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import Agent, Model, Provider


class CollectingClient(Client):
    def __init__(self):
        self.updates = []

    async def session_update(self, session_id, update, **kwargs):
        self.updates.append(update)

    async def request_permission(self, session_id, tool_call, options, **kwargs):
        return {"outcome": {"outcome": "cancelled"}}


async def test_acp_stdio_end_to_end(tmp_path):
    db_path = tmp_path / "acp.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine, factory = create_engine_and_sessionmaker(url)
    await init_db(engine)
    async with factory() as db:
        db.add(Provider(id="prov", name="test", kind="test"))
        db.add(Model(id="m", provider_id="prov", name="test-model"))
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
        await db.commit()
    await engine.dispose()

    client = CollectingClient()  # ty: ignore[abstract-class-instantiation]
    async with spawn_agent_process(
        client,
        sys.executable,
        "-m",
        "agentbox_api.acp_server",
        "--agent",
        "acp-test",
        env={**os.environ, "DATABASE_URL": url},
        cwd=str(tmp_path),
    ) as (conn, _proc):
        await conn.initialize(protocol_version=PROTOCOL_VERSION)
        session = await conn.new_session(cwd=str(tmp_path), mcp_servers=[])
        resp = await conn.prompt(
            session_id=session.session_id,
            prompt=[s.TextContentBlock(text="hi")],
        )
        assert resp.stop_reason == "end_turn"
        text = "".join(
            u.content.text
            for u in client.updates
            if getattr(u, "session_update", None) == "agent_message_chunk"
        )
        assert "Hello from the test provider" in text


async def test_acp_close_session_stops_mcp_manager(monkeypatch):
    from agentbox_harness.tools.mcp_session import McpSessionManager

    closed: list[str] = []

    async def fake_close(self, session_id):
        closed.append(session_id)

    class FakeJobs:
        async def kill_session(self, session_id):
            return None

    async def fake_cancel_sub_sessions(factory, session_id):
        return None

    monkeypatch.setattr(McpSessionManager, "close_session", fake_close)
    monkeypatch.setattr(
        "agentbox_api.acp_server.get_job_manager", lambda: FakeJobs()
    )
    monkeypatch.setattr(
        "agentbox_api.subsessions.cancel_sub_sessions", fake_cancel_sub_sessions
    )

    from agentbox_api.acp_server import AgentboxAcpAgent

    agent = AgentboxAcpAgent("acp-test", None, None)
    await agent.close_session("s1")
    assert "s1" in closed
