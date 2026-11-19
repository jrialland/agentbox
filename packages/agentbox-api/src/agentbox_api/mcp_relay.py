"""Session-scoped MCP relay for MCP Apps.

All app content (HTML, app resource reads, app tool calls) is proxied by the
backend, so the browser never contacts the MCP server directly.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from pydantic_ai.mcp import MCPToolset

from agentbox_harness.spec import AgentSpec, McpToolBinding
from agentbox_harness.tools.mcp import mcp_toolset_id


def mcp_binding_for(spec: AgentSpec, server_id: str) -> McpToolBinding:
    for binding in spec.tool_bindings:
        if isinstance(binding, McpToolBinding) and mcp_toolset_id(binding) == server_id:
            return binding
    logger.error("mcp server not found server={}", server_id)
    raise KeyError(server_id)


def _toolset(binding: McpToolBinding) -> MCPToolset:
    return MCPToolset(binding.server_url, id=mcp_toolset_id(binding))


async def read_resource_for_app(
    spec: AgentSpec, server_id: str, uri: str
) -> Any:
    toolset = _toolset(mcp_binding_for(spec, server_id))
    async with toolset:
        try:
            return await toolset.read_resource_for_app(uri)
        except Exception:
            logger.exception(
                "mcp resource read failed server={} uri={}", server_id, uri
            )
            raise


async def call_tool_for_app(
    spec: AgentSpec, server_id: str, name: str, arguments: dict
) -> Any:
    toolset = _toolset(mcp_binding_for(spec, server_id))
    async with toolset:
        try:
            return await toolset.call_tool_for_app(name, arguments)
        except Exception:
            logger.exception(
                "mcp tool call failed server={} tool={}", server_id, name
            )
            raise
