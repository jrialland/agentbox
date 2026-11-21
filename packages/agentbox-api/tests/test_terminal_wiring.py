from agentbox_api.runtime import delete_session_data
from agentbox_api.skills import prepare_agent
from agentbox_harness.spec import Mode
from agentbox_harness.tools.terminal import TERMINAL_TOOL_NAMES
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import Agent, Model, Provider


async def _prepared(tmp_path, session_id):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(Provider(id="prov", name="prov", kind="test"))
        s.add(Model(id="m1", provider_id="prov", name="test-model"))
        s.add(
            Agent(
                id="ag",
                name="bot",
                description="d",
                instructions="i",
                model_id="m1",
                tool_bindings='[{"name": "run_command"}]',
            )
        )
        await s.commit()
    prepared = await prepare_agent(
        factory,
        "bot",
        str(tmp_path),
        str(tmp_path / "skills"),
        session_id=session_id,
    )
    return engine, prepared


async def test_prepare_agent_registers_terminal_bundle(tmp_path):
    engine, prepared = await _prepared(tmp_path, "s1")
    try:
        ask = {
            tool.__name__
            for tool in prepared.registry.select_tools(
                Mode(name="ask", flags={"write": False})
            )
        }
        agent = {
            tool.__name__
            for tool in prepared.registry.select_tools(
                Mode(name="agent", flags={"write": True})
            )
        }
        assert not (set(TERMINAL_TOOL_NAMES) & ask)
        assert set(TERMINAL_TOOL_NAMES) <= agent
        bindings = {
            binding.name
            for binding in prepared.spec.tool_bindings
            if hasattr(binding, "name")
        }
        assert set(TERMINAL_TOOL_NAMES) <= bindings
    finally:
        await engine.dispose()


async def test_delete_session_data_kills_jobs(monkeypatch):
    class FakeManager:
        def __init__(self):
            self.killed = []

        async def kill_session(self, session_id):
            self.killed.append(session_id)

    fake = FakeManager()
    monkeypatch.setattr("agentbox_api.runtime.get_job_manager", lambda: fake)
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    try:
        await delete_session_data(factory, "s1")
        assert fake.killed == ["s1"]
    finally:
        await engine.dispose()

async def test_delete_session_data_closes_mcp(monkeypatch):
    from agentbox_harness.tools.mcp_session import McpSessionManager

    closed: list[str] = []

    async def fake_close(self, session_id):
        closed.append(session_id)

    monkeypatch.setattr(McpSessionManager, "close_session", fake_close)
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    try:
        await delete_session_data(factory, "s1")
        assert "s1" in closed
    finally:
        await engine.dispose()
