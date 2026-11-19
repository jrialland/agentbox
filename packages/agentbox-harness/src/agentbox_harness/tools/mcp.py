import re

from fastmcp.client.transports import StdioTransport
from loguru import logger
from pydantic_ai.mcp import MCPToolset

from agentbox_harness.spec import McpToolBinding


def mcp_toolset_id(binding: McpToolBinding) -> str:
    """Stable server id used to route MCP App relay requests."""
    return binding.id or _slug(binding.server_url) or "mcp"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def build_mcp_toolset(binding: McpToolBinding) -> MCPToolset:
    logger.debug("mcp toolset built id={} stdio={}", mcp_toolset_id(binding), bool(binding.command))
    if binding.command:
        transport = StdioTransport(
            command=binding.command,
            args=binding.args,
            env=binding.env or None,
        )
        return MCPToolset(transport, id=mcp_toolset_id(binding))
    return MCPToolset(binding.server_url, id=mcp_toolset_id(binding))
