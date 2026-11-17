from pydantic_ai import Agent

from agentbox_harness.spec import AgentSpec, McpToolBinding, Mode, NativeToolBinding
from agentbox_harness.tools.mcp import build_mcp_toolset
from agentbox_harness.tools.registry import ToolRegistry


def build_agent(
    spec: AgentSpec,
    mode: Mode,
    registry: ToolRegistry,
    model: str,
) -> Agent:
    native_names: set[str] = set()
    mcp_bindings: list[McpToolBinding] = []
    for binding in spec.tool_bindings:
        if isinstance(binding, NativeToolBinding):
            native_names.add(binding.name)
        elif isinstance(binding, McpToolBinding):
            mcp_bindings.append(binding)

    tools = registry.select_tools(mode, names=native_names)
    toolsets = [build_mcp_toolset(b) for b in mcp_bindings]
    return Agent(
        model=model,
        name=spec.name,
        instructions=spec.instructions,
        tools=tools,
        toolsets=toolsets,
    )
