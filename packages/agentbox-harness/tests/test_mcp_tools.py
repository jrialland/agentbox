from agentbox_harness.spec import McpToolBinding
from agentbox_harness.tools.mcp import build_mcp_toolset, mcp_toolset_id, resolve_mcp_env


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


def test_stdio_binding_builds_toolset():
    binding = McpToolBinding(id="fs", command="python", args=["-m", "srv"], env={"K": "V"})
    assert mcp_toolset_id(binding) == "fs"
    assert build_mcp_toolset(binding) is not None


def test_stdio_binding_passes_cwd_and_merged_env(monkeypatch):
    monkeypatch.setenv("HOST_TOKEN", "host-secret")
    binding = McpToolBinding(
        id="fs",
        command="python",
        args=["-m", "srv"],
        env={"K": "V", "HOST_TOKEN": "explicit-wins"},
        env_passthrough=["HOST_TOKEN", "NOT_SET"],
    )
    ts = build_mcp_toolset(binding, cwd="/tmp/project")
    transport = ts.client.transport
    assert transport.cwd == "/tmp/project"
    assert transport.env == {"HOST_TOKEN": "explicit-wins", "K": "V"}


def test_resolve_mcp_env_skips_missing_names(monkeypatch):
    monkeypatch.setenv("PRESENT", "1")
    binding = McpToolBinding(command="x", env_passthrough=["PRESENT", "MISSING"])
    assert resolve_mcp_env(binding) == {"PRESENT": "1"}
