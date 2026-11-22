import functools
import inspect
from collections.abc import Callable

from loguru import logger
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.capabilities import ProcessHistory
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
        build_subagent_session_tools(
            mode, subagent_session_runner, session_id
        )
    )
    tools = [_guard_tool(tool) for tool in tools]
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
