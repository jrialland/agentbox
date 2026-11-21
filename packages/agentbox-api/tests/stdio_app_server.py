"""A minimal real stdio MCP server for API integration tests."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("agentbox-test-api-stdio")


@mcp.tool()
def echo(text: str) -> str:
    """Echo text back."""
    return f"echo:{text}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
