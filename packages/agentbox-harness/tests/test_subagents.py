from pydantic_ai import Agent

from agentbox_harness.subagents import build_subagent_tool


async def test_subagent_tool_delegates():
    sub = Agent("test", name="sub", instructions="You are a sub-agent.")
    tool = build_subagent_tool(sub)

    class FakeCtx:
        usage = None

    result = await tool(FakeCtx(), "do the thing")
    assert result is not None
