import os
import re

from fastmcp.client.transports import StdioTransport
from loguru import logger
from pydantic_ai.mcp import MCPToolset

from agentbox_harness.spec import McpToolBinding


def mcp_toolset_id(binding: McpToolBinding) -> str:
    """Stable server id used to route MCP App relay requests."""
    return binding.id or _slug(binding.server_url) or _slug(binding.command) or "mcp"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def resolve_mcp_env(binding: McpToolBinding) -> dict[str, str]:
    merged = {
        name: os.environ[name]
        for name in binding.env_passthrough
        if name in os.environ
    }
    merged.update(binding.env)
    return merged


def build_mcp_toolset(binding: McpToolBinding, *, cwd: str | None = None) -> MCPToolset:
    logger.debug("mcp toolset built id={} stdio={}", mcp_toolset_id(binding), bool(binding.command))
    if binding.command:
        transport = StdioTransport(
            command=binding.command,
            args=binding.args,
            env=resolve_mcp_env(binding) or None,
            cwd=cwd or binding.cwd or None,
        )
        return MCPToolset(transport, id=mcp_toolset_id(binding))
    return MCPToolset(binding.server_url, id=mcp_toolset_id(binding))
