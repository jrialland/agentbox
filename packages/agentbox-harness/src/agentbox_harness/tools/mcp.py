"""Build MCP toolsets from Agent configuration bindings.

Selects stdio, SSE, or streamable HTTP transport from the binding and resolves
the environment variables passed to stdio servers.
"""

import os
import re

from fastmcp.client.transports import (
    SSETransport,
    StdioTransport,
    StreamableHttpTransport,
)
from loguru import logger
from pydantic_ai.mcp import MCPToolset

from agentbox_harness.spec import McpToolBinding


def mcp_toolset_id(binding: McpToolBinding) -> str:
    """Stable server id used to route MCP App relay requests."""
    return binding.id or _slug(binding.server_url) or _slug(binding.command) or "mcp"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def resolve_mcp_env(binding: McpToolBinding) -> dict[str, str]:
    """Merge passed-through environment variables with configured values.

    Only pass-through names that exist in the process environment are copied;
    explicit ``env`` values win on conflicts.

    Args:
        binding: MCP binding whose environment should be resolved.

    Returns:
        Environment variables to pass to a stdio server.
    """
    merged = {
        name: os.environ[name]
        for name in binding.env_passthrough
        if name in os.environ
    }
    merged.update(binding.env)
    return merged


def build_mcp_toolset(binding: McpToolBinding, *, cwd: str | None = None) -> MCPToolset:
    """Build an MCP toolset for a binding.

    A ``command`` selects stdio transport; otherwise ``transport`` picks SSE or
    streamable HTTP, defaulting to the client's default HTTP transport.

    Args:
        binding: MCP server binding to materialize.
        cwd: Working directory override for stdio servers.

    Returns:
        An MCP toolset that connects when entered.
    """
    logger.debug("mcp toolset built id={} stdio={}", mcp_toolset_id(binding), bool(binding.command))
    # A command always means a local stdio server; remote transports are chosen
    # by the binding's transport field.
    if binding.command:
        transport = StdioTransport(
            command=binding.command,
            args=binding.args,
            env=resolve_mcp_env(binding) or None,
            cwd=cwd or binding.cwd or None,
        )
        return MCPToolset(transport, id=mcp_toolset_id(binding))
    headers = binding.headers or None
    # Remote servers pick their wire transport from the binding; an unknown or
    # unset value falls through to the client's default HTTP transport.
    if binding.transport == "sse":
        return MCPToolset(
            SSETransport(binding.server_url, headers=headers),
            id=mcp_toolset_id(binding),
        )
    if binding.transport == "streamable-http":
        return MCPToolset(
            StreamableHttpTransport(binding.server_url, headers=headers),
            id=mcp_toolset_id(binding),
        )
    return MCPToolset(
        binding.server_url,
        id=mcp_toolset_id(binding),
        headers=headers,
    )
