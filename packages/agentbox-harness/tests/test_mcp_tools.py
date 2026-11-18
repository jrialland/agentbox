from agentbox_harness.spec import McpToolBinding
from agentbox_harness.tools.mcp import build_mcp_toolset, mcp_toolset_id


def test_build_mcp_toolset_from_binding():
    binding = McpToolBinding(server_url="https://example.com/mcp", tool_prefix="fs")
    ts = build_mcp_toolset(binding)
    assert ts is not None


def test_mcp_toolset_id_slugs_url():
    binding = McpToolBinding(server_url="http://localhost:9000/mcp")
    assert mcp_toolset_id(binding) == "http-localhost-9000-mcp"


def test_mcp_toolset_id_uses_explicit_id():
    binding = McpToolBinding(server_url="http://localhost:9000/mcp", id="test-app")
    assert mcp_toolset_id(binding) == "test-app"
    assert build_mcp_toolset(binding).id == "test-app"
