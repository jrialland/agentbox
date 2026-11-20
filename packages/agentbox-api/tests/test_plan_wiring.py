from agentbox_api.plan_tools import PLAN_TOOL_NAMES
from agentbox_api.skills import prepare_agent
from agentbox_harness.spec import Mode
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import Agent, Model, Provider


async def test_prepare_agent_exposes_plan_tools(tmp_path):
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
        tools = prepared.registry.select_tools(
            Mode(name="ask", flags={"write": False})
        )
        names = {tool.__name__ for tool in tools}  # ty: ignore[missing-attribute]
        assert set(PLAN_TOOL_NAMES) <= names
        bindings = {
            binding.name
            for binding in prepared.spec.tool_bindings
            if hasattr(binding, "name")
        }
        assert set(PLAN_TOOL_NAMES) <= bindings
        todo_list = next(tool for tool in tools if tool.__name__ == "todo_list")  # ty: ignore[missing-attribute]
        assert await todo_list() == "TODO list is empty."
    finally:
        await engine.dispose()
