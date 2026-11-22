import os
import sys

from acp import PROTOCOL_VERSION, Client, spawn_agent_process
from acp import schema as s

from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import Agent, Model, Provider


class CollectingClient(Client):
    def __init__(self):
        self.updates = []
        self.calls = []

    async def session_update(self, session_id, update, **kwargs):
        self.updates.append(update)

    async def request_permission(self, session_id, tool_call, options, **kwargs):
        return {"outcome": {"outcome": "cancelled"}}

    async def read_text_file(self, session_id, path, line=None, limit=None, **kwargs):
        self.calls.append(("read_text_file", session_id, path))
        return s.ReadTextFileResponse(content="client file content")

    async def write_text_file(self, session_id, path, content, **kwargs):
        self.calls.append(("write_text_file", session_id, path, content))
        return None

    async def create_terminal(
        self,
        session_id,
        command,
        args=None,
        env=None,
        cwd=None,
        output_byte_limit=None,
        **kwargs,
    ):
        self.calls.append(("create_terminal", session_id, command, args, cwd))
        return s.CreateTerminalResponse(terminal_id="term-1")

    async def wait_for_terminal_exit(self, session_id, terminal_id, **kwargs):
        self.calls.append(("wait_for_terminal_exit", session_id, terminal_id))
        return s.WaitForTerminalExitResponse(exit_code=0)

    async def terminal_output(self, session_id, terminal_id, **kwargs):
        self.calls.append(("terminal_output", session_id, terminal_id))
        return s.TerminalOutputResponse(
            output="client terminal output",
            truncated=False,
        )

    async def kill_terminal(self, session_id, terminal_id, **kwargs):
        self.calls.append(("kill_terminal", session_id, terminal_id))

    async def release_terminal(self, session_id, terminal_id, **kwargs):
        self.calls.append(("release_terminal", session_id, terminal_id))


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

    async def fake_cancel_subagent_sessions(factory, session_id):
        return None

    monkeypatch.setattr(McpSessionManager, "close_session", fake_close)
    monkeypatch.setattr(
        "agentbox_api.acp_server.get_job_manager", lambda: FakeJobs()
    )
    monkeypatch.setattr(
        "agentbox_api.subagent_sessions.cancel_subagent_sessions", fake_cancel_subagent_sessions
    )

    from agentbox_api.acp_server import AgentboxAcpAgent

    agent = AgentboxAcpAgent("acp-test", None, None)
    await agent.close_session("s1")
    assert "s1" in closed

async def test_acp_stdio_uses_client_filesystem(tmp_path):
    db_path = tmp_path / "acp-fs.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine, factory = create_engine_and_sessionmaker(url)
    await init_db(engine)
    async with factory() as db:
        db.add(Provider(id="prov", name="test", kind="test_acp_fs"))
        db.add(Model(id="m", provider_id="prov", name="test-model"))
        db.add(
            Agent(
                id="ag",
                name="acp-fs",
                description="",
                instructions="",
                model_id="m",
                tool_bindings='[{"name":"read_text_file"}]',
                mode_definitions='[{"name":"agent","flags":{"write":true}}]',
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
        "acp-fs",
        env={**os.environ, "DATABASE_URL": url},
        cwd=str(tmp_path),
    ) as (conn, _proc):
        await conn.initialize(
            protocol_version=PROTOCOL_VERSION,
            client_capabilities=s.ClientCapabilities(
                fs=s.FileSystemCapabilities(
                    read_text_file=True, write_text_file=True
                )
            ),
        )
        session = await conn.new_session(cwd=str(tmp_path), mcp_servers=[])
        resp = await conn.prompt(
            session_id=session.session_id,
            prompt=[s.TextContentBlock(text="read")],
        )
        assert resp.stop_reason == "end_turn"
        assert any(call[0] == "read_text_file" for call in client.calls)


async def test_acp_stdio_uses_client_terminal(tmp_path):
    db_path = tmp_path / "acp-terminal.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine, factory = create_engine_and_sessionmaker(url)
    await init_db(engine)
    async with factory() as db:
        db.add(Provider(id="prov", name="test", kind="test_acp_terminal"))
        db.add(Model(id="m", provider_id="prov", name="test-model"))
        db.add(
            Agent(
                id="ag",
                name="acp-terminal",
                description="",
                instructions="",
                model_id="m",
                tool_bindings='[{"name":"run_command"}]',
                mode_definitions='[{"name":"agent","flags":{"write":true}}]',
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
        "acp-terminal",
        env={**os.environ, "DATABASE_URL": url},
        cwd=str(tmp_path),
    ) as (conn, _proc):
        await conn.initialize(
            protocol_version=PROTOCOL_VERSION,
            client_capabilities=s.ClientCapabilities(terminal=True),
        )
        session = await conn.new_session(cwd=str(tmp_path), mcp_servers=[])
        resp = await conn.prompt(
            session_id=session.session_id,
            prompt=[s.TextContentBlock(text="run")],
        )
        assert resp.stop_reason == "end_turn"
        assert any(call[0] == "create_terminal" for call in client.calls)
        assert any(call[0] == "release_terminal" for call in client.calls)
