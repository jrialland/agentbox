from collections.abc import Callable

from loguru import logger
from pydantic_ai import Agent
from pydantic_ai.models import Model

from agentbox_harness.spec import AgentSpec, McpToolBinding, Mode, NativeToolBinding
from agentbox_harness.subagents import build_subagent_tool
from agentbox_harness.tools.mcp import build_mcp_toolset
from agentbox_harness.tools.registry import ToolRegistry


def build_subagent_tools(
    spec: AgentSpec,
    sub_agents: dict[str, AgentSpec] | None,
    registry: ToolRegistry,
    model: Model,
    depth: int = 0,
    max_depth: int = 3,
) -> list[Callable]:
    tools: list[Callable] = []
    if depth >= max_depth or not sub_agents:
        return tools
    for sub_id in spec.sub_agent_ids:
        sub_spec = sub_agents.get(sub_id)
        if sub_spec is None:
            continue
        sub_agent = build_agent(
            sub_spec,
            Mode(name="subagent", flags={}),
            registry,
            model,
            sub_agents=sub_agents,
            depth=depth + 1,
            max_depth=max_depth,
        )
        tools.append(build_subagent_tool(sub_agent))
    return tools


def build_agent(
    spec: AgentSpec,
    mode: Mode,
    registry: ToolRegistry,
    model: Model,
    sub_agents: dict[str, AgentSpec] | None = None,
    depth: int = 0,
    max_depth: int = 3,
) -> Agent:
    native_names: set[str] = set()
    mcp_bindings: list[McpToolBinding] = []
    for binding in spec.tool_bindings:
        if isinstance(binding, NativeToolBinding):
            native_names.add(binding.name)
        elif isinstance(binding, McpToolBinding):
            mcp_bindings.append(binding)

    tools = registry.select_tools(mode, names=native_names)
    tools.extend(
        build_subagent_tools(spec, sub_agents, registry, model, depth, max_depth)
    )
    toolsets = [build_mcp_toolset(b) for b in mcp_bindings]
    logger.debug("agent built name={} tools={} toolsets={}", spec.name, len(tools), len(toolsets))
    return Agent(
        model=model,
        name=spec.name,
        instructions=spec.instructions,
        tools=tools,
        toolsets=toolsets,
    )
