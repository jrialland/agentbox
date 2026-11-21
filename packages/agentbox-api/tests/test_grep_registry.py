from agentbox_api.runtime import build_registry
from agentbox_harness.spec import Mode


def test_grep_is_registered_as_read_tool(tmp_path):
    registry = build_registry(str(tmp_path))
    names = {
        getattr(tool, "__name__", "")
        for tool in registry.select_tools(Mode(name="ask", flags={"write": False}))
    }
    assert "grep" in names
