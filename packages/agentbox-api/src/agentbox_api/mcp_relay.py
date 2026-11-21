"""Session-scoped MCP relay for MCP Apps.

All app content (HTML, app resource reads, app tool calls) is proxied by the
backend, so the browser never contacts the MCP server directly.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from pydantic_ai.mcp import MCPToolset

from agentbox_harness.logging import log_exception
from agentbox_harness.spec import AgentSpec, McpToolBinding
from agentbox_harness.tools.mcp import mcp_toolset_id
from agentbox_harness.tools.mcp_session import McpSessionManager


def mcp_binding_for(spec: AgentSpec, server_id: str) -> McpToolBinding:
    for binding in spec.tool_bindings:
        if isinstance(binding, McpToolBinding) and mcp_toolset_id(binding) == server_id:
            return binding
    logger.error("mcp server not found server={}", server_id)
    raise KeyError(server_id)


async def _toolset(
    manager: McpSessionManager,
    session_id: str,
    project_root: str,
    spec: AgentSpec,
    server_id: str,
    extra_roots: list[str] | None = None,
) -> tuple[MCPToolset, bool]:
    binding = mcp_binding_for(spec, server_id)
    if binding.command:
        result = await manager.toolsets_for(
            session_id,
            [b for b in spec.tool_bindings if isinstance(b, McpToolBinding)],
            project_root,
            extra_roots,
        )
        for toolset in result.toolsets:
            if toolset.id == server_id:
                manager.touch(session_id)
                return toolset, False
        for warning in result.warnings:
            if warning.server_id == server_id:
                raise RuntimeError(warning.message)
        raise KeyError(server_id)
    return MCPToolset(binding.server_url, id=mcp_toolset_id(binding)), True


async def read_resource_for_app(
    manager: McpSessionManager,
    session_id: str,
    project_root: str,
    spec: AgentSpec,
    server_id: str,
    uri: str,
    extra_roots: list[str] | None = None,
) -> Any:
    toolset, owned = await _toolset(
        manager, session_id, project_root, spec, server_id, extra_roots
    )
    try:
        if owned:
            async with toolset:
                return await toolset.read_resource_for_app(uri)
        return await toolset.read_resource_for_app(uri)
    except Exception:
        log_exception("mcp resource read failed server={} uri={}", server_id, uri)
        raise


async def call_tool_for_app(
    manager: McpSessionManager,
    session_id: str,
    project_root: str,
    spec: AgentSpec,
    server_id: str,
    name: str,
    arguments: dict,
    extra_roots: list[str] | None = None,
) -> Any:
    toolset, owned = await _toolset(
        manager, session_id, project_root, spec, server_id, extra_roots
    )
    try:
        if owned:
            async with toolset:
                return await toolset.call_tool_for_app(name, arguments)
        return await toolset.call_tool_for_app(name, arguments)
    except Exception:
        log_exception("mcp tool call failed server={} tool={}", server_id, name)
        raise
