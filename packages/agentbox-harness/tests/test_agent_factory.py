from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.test import TestModel

from agentbox_harness.agent_factory import build_agent
from agentbox_harness.spec import (
    AgentSpec,
    McpToolBinding,
    Mode,
    ModelBinding,
    NativeToolBinding,
)
from agentbox_harness.tools.registry import ToolRegistry


async def write_file(path: str, content: str) -> str:
    return "ok"


def _spec(tool_bindings=None) -> AgentSpec:
    return AgentSpec(
        name="coder",
        description="writes code",
        instructions="Be helpful.",
        tool_bindings=tool_bindings or [],
        model_binding=ModelBinding(model="test", provider="test"),
    )


def test_build_agent_sets_instructions_and_tools():
    reg = ToolRegistry()
    reg.register_native("write_file", write_file, required_flags=("write",))

    spec = _spec([NativeToolBinding(name="write_file")])
    agent = build_agent(spec, Mode(name="agent", flags={"write": True}), reg, TestModel())

    assert isinstance(agent, Agent)
    result = agent.run_sync("hi", model=TestModel())
    assert result is not None


def test_build_agent_attaches_mcp_toolsets():
    reg = ToolRegistry()
    spec = _spec([McpToolBinding(server_url="https://example.com/mcp")])

    agent = build_agent(spec, Mode(name="agent", flags={}), reg, TestModel())

    mcp = [t for t in agent.toolsets if isinstance(t, MCPToolset)]
    assert len(mcp) == 1
