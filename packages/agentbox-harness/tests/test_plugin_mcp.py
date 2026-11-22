from agentbox_harness.spec import (
    AgentSpec,
    McpToolBinding,
    ModelBinding,
    PluginMcpBinding,
)
from agentbox_harness.tools.mcp import build_mcp_toolset


def test_agent_spec_round_trips_plugin_mcp_reference():
    spec = AgentSpec(
        name="coder",
        description="d",
        instructions="i",
        tool_bindings=[],
        plugin_mcp_bindings=[
            PluginMcpBinding(
                plugin="acme-tools",
                server="local",
                project_id="p1",
                id="acme-tools:local",
            )
        ],
        model_binding=ModelBinding(model="test", provider="test"),
    )
    dumped = spec.model_dump()
    assert dumped["plugin_mcp_bindings"][0]["project_id"] == "p1"
    loaded = AgentSpec.model_validate(dumped)
    assert loaded.plugin_mcp_bindings[0].plugin == "acme-tools"
    assert loaded.plugin_mcp_bindings[0].server == "local"


def test_build_mcp_toolset_uses_explicit_sse_transport():
    binding = McpToolBinding(
        id="acme-tools:remote",
        server_url="https://example.test/sse",
        transport="sse",
        headers={"X-Tenant": "public"},
    )
    toolset = build_mcp_toolset(binding)
    assert toolset.id == "acme-tools:remote"


def test_build_mcp_toolset_uses_streamable_http_transport():
    binding = McpToolBinding(
        id="acme-tools:remote",
        server_url="https://example.test/mcp",
        transport="streamable-http",
        headers={"X-Tenant": "public"},
    )
    toolset = build_mcp_toolset(binding)
    assert toolset.id == "acme-tools:remote"
