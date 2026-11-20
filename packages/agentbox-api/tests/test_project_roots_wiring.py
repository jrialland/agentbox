from agentbox_api.skills import prepare_agent
from agentbox_harness.spec import Mode
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import Agent, Model, Provider


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
            s.add(Model(id="m1", provider_id="prov", name="test-model"))
            s.add(
                Agent(
                    id="ag",
                    name="bot",
                    description="d",
                    instructions="i",
                    model_id="m1",
                    tool_bindings='[{"name": "write_file"}, {"name": "list_allowed_directories"}]',
                )
            )
            await s.commit()
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
