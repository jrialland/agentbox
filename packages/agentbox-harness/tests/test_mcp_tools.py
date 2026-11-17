from agentbox_harness.spec import McpToolBinding
from agentbox_harness.tools.mcp import build_mcp_toolset


def test_build_mcp_toolset_from_binding():
    binding = McpToolBinding(server_url="https://example.com/mcp", tool_prefix="fs")
    ts = build_mcp_toolset(binding)
    assert ts is not None
