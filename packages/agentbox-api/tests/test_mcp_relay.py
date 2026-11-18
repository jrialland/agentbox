"""MCP relay tests against a real (HTTP) test MCP server."""

from __future__ import annotations

import pytest
from mcp_app_server import APP_URI

from agentbox_api import mcp_relay
from agentbox_harness.spec import AgentSpec, McpToolBinding, ModelBinding


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
        _spec(mcp_server_url), "test-app", APP_URI
    )
    assert "Hello MCP App" in result["contents"][0]["text"]


async def test_relay_calls_app_tool(mcp_server_url):
    result = await mcp_relay.call_tool_for_app(
        _spec(mcp_server_url), "test-app", "show_app", {"text": "x"}
    )
    assert "App result: x" in result["content"][0]["text"]


async def test_relay_unknown_server_errors(mcp_server_url):
    with pytest.raises(KeyError):
        await mcp_relay.read_resource_for_app(_spec(mcp_server_url), "missing", APP_URI)
