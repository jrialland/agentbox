from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset

from agentbox_harness.spec import McpToolBinding


def build_mcp_toolset(binding: McpToolBinding) -> MCPToolset:
    return MCPToolset(binding.server_url)


def attach_mcp_toolsets(agent: Agent, bindings: list[McpToolBinding]) -> None:
    for binding in bindings:
        agent.toolsets.append(build_mcp_toolset(binding))
