from agentbox_harness.spec import (
    DEFAULT_MODES,
    AgentSpec,
    ModelBinding,
    NativeToolBinding,
)
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.repos.agents import AgentRepository
from agentbox_models.tables.core import Model, Provider


async def test_agent_spec_roundtrip():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(Provider(id="prov1", name="openai", kind="openai_responses"))
        s.add(Model(id="m1", provider_id="prov1", name="gpt-4o"))
        await s.commit()

    repo = AgentRepository(factory)
    spec = AgentSpec(
        name="coder",
        description="d",
        instructions="i",
        tool_bindings=[NativeToolBinding(name="write_file")],
        mode_definitions=list(DEFAULT_MODES),
        model_binding=ModelBinding(model="gpt-4o", provider="openai"),
    )
    await repo.save(spec)
    loaded = await repo.load("coder")
    assert loaded is not None
    assert loaded.name == spec.name
    assert loaded.model_binding.model == "gpt-4o"
    assert isinstance(loaded.tool_bindings[0], NativeToolBinding)
    assert loaded.tool_bindings[0].name == "write_file"
    assert loaded.mode_definitions[0].name == "ask"
    await engine.dispose()
