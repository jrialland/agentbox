"""MCP relay tests against real (HTTP and stdio) test MCP servers."""

from __future__ import annotations

import pathlib
import sys

import pytest
from mcp_app_server import APP_URI

from agentbox_api import mcp_relay
from agentbox_harness.spec import AgentSpec, McpToolBinding, ModelBinding
from agentbox_harness.tools.mcp_session import McpSessionManager


def _spec(url: str) -> AgentSpec:
    return AgentSpec(
        name="app-agent",
        description="",
        instructions="",
        tool_bindings=[McpToolBinding(server_url=url, id="test-app")],
        model_binding=ModelBinding(model="test", provider="test"),
    )


async def test_relay_reads_app_resource(mcp_server_url):
    result = await mcp_relay.read_resource_for_app(
        McpSessionManager(), "s1", "/tmp", _spec(mcp_server_url), "test-app", APP_URI
    )
    assert "Hello MCP App" in result["contents"][0]["text"]


async def test_relay_calls_app_tool(mcp_server_url):
    result = await mcp_relay.call_tool_for_app(
        McpSessionManager(),
        "s1",
        "/tmp",
        _spec(mcp_server_url),
        "test-app",
        "show_app",
        {"text": "x"},
    )
    assert "App result: x" in result["content"][0]["text"]


async def test_relay_unknown_server_errors(mcp_server_url):
    with pytest.raises(KeyError):
        await mcp_relay.read_resource_for_app(
            McpSessionManager(), "s1", "/tmp", _spec(mcp_server_url), "missing", APP_URI
        )


async def test_relay_reads_stdio_app_resource(tmp_path):
    server = tmp_path / "stdio_app.py"
    server.write_text(
        "from mcp.server.mcpserver import MCPServer\n"
        "mcp = MCPServer('app')\n"
        "@mcp.resource('ui://stdio/app.html', mime_type='text/html;profile=mcp-app')\n"
        "def app() -> str:\n"
        "    return '<h1>stdio app</h1>'\n"
        "if __name__ == '__main__':\n"
        "    mcp.run(transport='stdio')\n",
        encoding="utf-8",
    )
    spec = AgentSpec(
        name="a",
        description="",
        instructions="",
        tool_bindings=[
            McpToolBinding(
                id="stdio-app",
                command=sys.executable,
                args=[str(pathlib.Path(server))],
            )
        ],
        model_binding=ModelBinding(model="t", provider="t"),
    )
    manager = McpSessionManager(start_timeout=20)
    try:
        result = await mcp_relay.read_resource_for_app(
            manager,
            "s1",
            str(tmp_path),
            spec,
            "stdio-app",
            "ui://stdio/app.html",
        )
        assert "stdio app" in result["contents"][0]["text"]
    finally:
        await manager.close_session("s1")
