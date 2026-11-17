from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from agentbox_harness.agent_factory import build_agent
from agentbox_harness.spec import AgentSpec, Mode, ModelBinding
from agentbox_harness.tools.registry import ToolRegistry


async def write_file(path: str, content: str) -> str:
    return "ok"


def _spec() -> AgentSpec:
    return AgentSpec(
        name="coder",
        description="writes code",
        instructions="Be helpful.",
        tool_bindings=[],
        model_binding=ModelBinding(model="test", provider="test"),
    )


def test_build_agent_sets_instructions_and_tools():
    reg = ToolRegistry()
    reg.register_native("write_file", write_file, required_flags=("write",))

    spec = _spec()
    agent = build_agent(spec, Mode(name="agent", flags={"write": True}), reg, "test")

    assert isinstance(agent, Agent)
    result = agent.run_sync("hi", model=TestModel())
    assert result is not None
