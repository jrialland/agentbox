from agentbox_api.skills import prepare_agent
from agentbox_harness.spec import (
    DEFAULT_MODES,
    AgentSpec,
    Mode,
    ModelBinding,
    NativeToolBinding,
)
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.repos.agents import AgentRepository
from agentbox_models.tables.core import Model, Provider


async def test_prepare_agent_grants_extra_write_root(tmp_path):
    project = tmp_path / "project"
    external = tmp_path / "external"
    project.mkdir()
    external.mkdir()
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    try:
        async with factory() as s:
            s.add(Provider(id="prov", name="prov", kind="test"))
            await s.flush()
            await s.flush()
            s.add(Model(id="m1", provider_id="prov", name="test-model"))
            await s.commit()
        await AgentRepository(factory).save(
            AgentSpec(
                name="bot",
                description="d",
                instructions="i",
                tool_bindings=[
                    NativeToolBinding(name="write_file"),
                    NativeToolBinding(name="list_allowed_directories"),
                ],
                mode_definitions=list(DEFAULT_MODES),
                model_binding=ModelBinding(model="test-model", provider=""),
            )
        )
        prepared = await prepare_agent(
            factory,
            "bot",
            str(project),
            str(tmp_path / "skills"),
            extra_roots=[str(external)],
        )
        tools = {
            tool.__name__: tool  # ty: ignore[missing-attribute]
            for tool in prepared.registry.select_tools(
                Mode(name="agent", flags={"write": True})
            )
        }
        await tools["write_file"](str(external / "x.txt"), "hello")
        assert (external / "x.txt").read_text(encoding="utf-8") == "hello"
        allowed = await tools["list_allowed_directories"]()
        assert str(external.resolve()) in allowed
    finally:
        await engine.dispose()
