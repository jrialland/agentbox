from pydantic_ai import Agent

from agentbox_harness.spec import AgentSpec, Mode
from agentbox_harness.tools.registry import ToolRegistry


def build_agent(
    spec: AgentSpec,
    mode: Mode,
    registry: ToolRegistry,
    model: str,
) -> Agent:
    tools = registry.select_tools(mode)
    return Agent(
        model=model,
        name=spec.name,
        instructions=spec.instructions,
        tools=tools,
    )
