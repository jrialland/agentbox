import re

from pydantic_ai.mcp import MCPToolset

from agentbox_harness.spec import McpToolBinding


def mcp_toolset_id(binding: McpToolBinding) -> str:
    """Stable server id used to route MCP App relay requests."""
    return binding.id or _slug(binding.server_url)


def _slug(url: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-") or "mcp"


def build_mcp_toolset(binding: McpToolBinding) -> MCPToolset:
    return MCPToolset(binding.server_url, id=mcp_toolset_id(binding))
