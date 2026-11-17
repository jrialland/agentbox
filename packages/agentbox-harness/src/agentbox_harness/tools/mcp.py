from pydantic_ai.mcp import MCPToolset

from agentbox_harness.spec import McpToolBinding


def build_mcp_toolset(binding: McpToolBinding) -> MCPToolset:
    return MCPToolset(binding.server_url)
