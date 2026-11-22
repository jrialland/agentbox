from agentbox_api.skills import prepare_agent
from agentbox_harness.lsp.diagnostics import get_diagnostics_service
from agentbox_harness.lsp.manager import get_lsp_manager
from agentbox_harness.spec import Mode
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import Agent, Model, Provider


async def test_prepare_agent_exposes_lsp_diagnostics_tool(tmp_path):
    worker = get_lsp_manager()
    diagnostics = get_diagnostics_service()
    old_enabled = worker.enabled
    old_mode = diagnostics.mode
    worker.enabled = True
    diagnostics.mode = "auto"
    diagnostics.enabled = True
    engine, factory = create_engine_and_sessionmaker(
        "sqlite+aiosqlite:///:memory:"
    )
    await init_db(engine)
    try:
        async with factory() as s:
            s.add(Provider(id="prov", name="prov", kind="test"))
            await s.flush()
            s.add(Model(id="m1", provider_id="prov", name="test-model"))
            await s.flush()
            s.add(
                Agent(
                    id="ag",
                    name="bot",
                    description="d",
                    instructions="i",
                    model_id="m1",
                )
            )
            await s.commit()
        prepared = await prepare_agent(
            factory,
            "bot",
            str(tmp_path),
            str(tmp_path / "skills"),
            session_id="s1",
        )
        bindings = {
            binding.name
            for binding in prepared.spec.tool_bindings
            if hasattr(binding, "name")
        }
        assert "lsp_diagnostics" in bindings
        tools = prepared.registry.select_tools(
            Mode(name="ask", flags={"write": False})
        )
        names = {tool.__name__ for tool in tools}  # ty: ignore[missing-attribute]
        assert "lsp_diagnostics" in names
    finally:
        worker.enabled = old_enabled
        diagnostics.mode = old_mode
        await engine.dispose()
