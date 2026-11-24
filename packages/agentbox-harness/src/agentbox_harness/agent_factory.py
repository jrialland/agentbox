"""Build pydantic-ai agents from an Agent configuration and mode.

The factory resolves native and MCP tools, wraps every native or
subagent-session tool with a retry guard, and attaches context-editing and
plugin capabilities before the harness hands the agent to the run manager.
"""

import functools
import inspect
from collections.abc import Callable

from loguru import logger
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.capabilities import AbstractCapability, ProcessHistory
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models import Model

from agentbox_harness.context_editing import (
    ContextEditingConfig,
    make_context_editing_processor,
)
from agentbox_harness.spec import AgentSpec, McpToolBinding, Mode, NativeToolBinding
from agentbox_harness.subagent_sessions import build_subagent_session_tools
from agentbox_harness.tools.mcp import build_mcp_toolset
from agentbox_harness.tools.registry import ToolRegistry


def _guard_tool(tool: Callable) -> Callable:
    name = getattr(tool, "__name__", "tool")

    @functools.wraps(tool)
    async def guarded(*args, **kwargs):
        try:
            result = tool(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result
        except ModelRetry:
            raise
        except Exception as exc:
            message = str(exc) or type(exc).__name__
            logger.warning("tool failed name={} error={}", name, message)
            raise ModelRetry(f"{name} failed: {message}") from exc

    return guarded


def build_agent(
    spec: AgentSpec,
    mode: Mode,
    registry: ToolRegistry,
    model: Model,
    subagent_session_runner=None,
    session_id: str | None = None,
    stdio_toolsets: list[MCPToolset] | None = None,
    context_editing: ContextEditingConfig | None = None,
    plugin_hooks: AbstractCapability | None = None,
) -> Agent:
    """Build the pydantic-ai agent used for one session run.

    Native tools come from the registry filtered by the mode, subagent-session
    tools are added when the mode allows them, MCP bindings become toolsets,
    and each tool is wrapped so failures surface to the model as retries.

    Args:
        spec: Agent configuration providing the name, instructions, and tool
            bindings.
        mode: Mode whose flags gate which native tools are eligible.
        registry: Tool registry used to resolve native tool bindings.
        model: Model the agent runs against.
        subagent_session_runner: Optional runner backing the subagent-session
            tools; tools are omitted when it is unset.
        session_id: Parent session id exposed to the subagent-session tools.
        stdio_toolsets: Pre-opened stdio MCP toolsets managed by the harness.
        context_editing: Optional context-editing configuration; a disabled
            configuration is ignored.
        plugin_hooks: Optional capability added after context editing.

    Returns:
        A configured pydantic-ai :class:`~pydantic_ai.Agent`.
    """
    native_names: set[str] = set()
    mcp_bindings: list[McpToolBinding] = []
    for binding in spec.tool_bindings:
        if isinstance(binding, NativeToolBinding):
            native_names.add(binding.name)
        elif isinstance(binding, McpToolBinding):
            mcp_bindings.append(binding)

    tools = registry.select_tools(mode, names=native_names)
    tools.extend(
        build_subagent_session_tools(
            mode, subagent_session_runner, session_id
        )
    )
    # Wrap only after native and subagent-session tools are assembled so every
    # tool shares the same retry guard rather than being wrapped piecemeal.
    tools = [_guard_tool(tool) for tool in tools]
    # Command-less bindings are always built here. Command-based bindings are
    # built here only when the caller supplies no managed stdio toolsets;
    # otherwise they are opened by the caller and arrive via stdio_toolsets.
    toolsets = [
        build_mcp_toolset(b)
        for b in mcp_bindings
        if not b.command or stdio_toolsets is None
    ]
    toolsets.extend(stdio_toolsets or [])
    capabilities = []
    if context_editing is not None and context_editing.enabled:
        capabilities.append(
            ProcessHistory(make_context_editing_processor(context_editing))
        )
    # Context editing is appended first; plugin hooks follow in registration
    # order.
    if plugin_hooks is not None:
        capabilities.append(plugin_hooks)
    logger.debug(
        "agent built name={} tools={} toolsets={} capabilities={}",
        spec.name,
        len(tools),
        len(toolsets),
        len(capabilities),
    )
    return Agent(
        model=model,
        name=spec.name,
        instructions=spec.instructions,
        tools=tools,
        toolsets=toolsets,
        capabilities=capabilities or None,
    )
