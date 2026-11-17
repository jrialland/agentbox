from agentbox_harness.spec import Mode
from agentbox_harness.tools.registry import ToolRegistry


async def read_file(path: str) -> str:
    return "data"


async def write_file(path: str, content: str) -> str:
    return "ok"


def test_select_tools_filters_by_flags():
    reg = ToolRegistry()
    reg.register_native("read_file", read_file, required_flags=("read",))
    reg.register_native("write_file", write_file, required_flags=("write",))

    ask = Mode(name="ask", flags={"write": False})
    agent = Mode(name="agent", flags={"write": True})

    assert [f.__name__ for f in reg.select_tools(ask)] == ["read_file"]
    assert {f.__name__ for f in reg.select_tools(agent)} == {"read_file", "write_file"}
