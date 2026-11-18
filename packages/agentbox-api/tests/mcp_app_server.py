"""A real MCP server exposing an MCP App tool + a ``ui://`` resource.

Used by the relay tests (over HTTP) and by the Playwright E2E ``webServer``.
Run standalone: ``uv run python tests/mcp_app_server.py [port]``.
"""

from __future__ import annotations

import asyncio

from mcp.server.mcpserver import MCPServer

APP_URI = "ui://test/app.html"


def build_server() -> MCPServer:
    mcp = MCPServer("agentbox-test-app")

    @mcp.tool(meta={"ui": {"resourceUri": APP_URI}})
    def show_app(text: str = "hello") -> str:
        """Render the demo MCP app."""
        return f"App result: {text}"

    @mcp.resource(APP_URI, mime_type="text/html;profile=mcp-app")
    def app_html() -> str:
        return (
            "<!doctype html><html><body><h1>Hello MCP App</h1>"
            "<p>Rendered in agentbox.</p></body></html>"
        )

    return mcp


def main(port: int = 9000) -> None:
    server = build_server()
    asyncio.run(server.run_streamable_http_async(host="127.0.0.1", port=port))


if __name__ == "__main__":
    import sys

    main(int(sys.argv[1]) if len(sys.argv) > 1 else 9000)
