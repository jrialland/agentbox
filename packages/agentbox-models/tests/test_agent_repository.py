from agentbox_harness.spec import (
    DEFAULT_MODES,
    AgentSpec,
    McpToolBinding,
    ModelBinding,
    NativeToolBinding,
)
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.repos.agents import AgentRepository
from agentbox_models.tables.core import Model, Provider


async def _seed(factory):
    async with factory() as s:
        s.add(Provider(id="p1", name="test", kind="generic"))
        await s.flush()
        s.add(Model(id="m1", provider_id="p1", name="test-model"))
        await s.commit()


async def test_agent_roundtrips_normalized_bindings_and_modes():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    await _seed(factory)
    repo = AgentRepository(factory)
    spec = AgentSpec(
        name="coder",
        description="d",
        instructions="i",
        tool_bindings=[
            NativeToolBinding(name="write_file", required_flags=("write",)),
            McpToolBinding(
                id="local",
                command="uvx",
                args=["server", "--flag"],
                env={"A": "1"},
                env_passthrough=["HOME"],
                cwd="/tmp",
            ),
        ],
        mode_definitions=list(DEFAULT_MODES),
        model_binding=ModelBinding(model="test-model", provider=""),
    )
    await repo.save(spec)
    loaded = await repo.load("coder")
    assert loaded is not None
    assert loaded.tool_bindings[0] == NativeToolBinding("write_file", ("write",))
    mcp = loaded.tool_bindings[1]
    assert isinstance(mcp, McpToolBinding)
    assert mcp.args == ["server", "--flag"]
    assert mcp.env == {"A": "1"}
    assert mcp.env_passthrough == ["HOME"]
    assert [m.name for m in loaded.mode_definitions] == ["ask", "agent"]
    assert loaded.mode_definitions[0].flags == {"write": False}
    await engine.dispose()
