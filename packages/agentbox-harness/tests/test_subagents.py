from pydantic_ai import Agent

from agentbox_harness.agent_factory import build_subagent_tools
from agentbox_harness.spec import AgentSpec, ModelBinding
from agentbox_harness.subagents import build_subagent_tool
from agentbox_harness.tools.registry import ToolRegistry


async def test_subagent_tool_delegates():
    sub = Agent("test", name="sub", instructions="You are a sub-agent.")
    tool = build_subagent_tool(sub)

    class FakeCtx:
        usage = None

    result = await tool(FakeCtx(), "do the thing")
    assert result is not None


def _spec(name: str, sub_agent_ids=None) -> AgentSpec:
    return AgentSpec(
        name=name,
        description="d",
        instructions="i",
        tool_bindings=[],
        sub_agent_ids=sub_agent_ids or [],
        model_binding=ModelBinding(model="test", provider="test"),
    )


def test_build_subagent_tools_injects_delegation_tool():
    reg = ToolRegistry()
    sub_spec = _spec("sub")
    parent = _spec("parent", sub_agent_ids=["sub"])

    tools = build_subagent_tools(parent, {"sub": sub_spec}, reg, "test")

    assert [getattr(t, "__name__") for t in tools] == ["delegate_sub"]


def test_build_subagent_tools_respects_max_depth():
    reg = ToolRegistry()
    sub_spec = _spec("sub")
    parent = _spec("parent", sub_agent_ids=["sub"])

    tools = build_subagent_tools(parent, {"sub": sub_spec}, reg, "test", depth=3, max_depth=3)
    assert tools == []
