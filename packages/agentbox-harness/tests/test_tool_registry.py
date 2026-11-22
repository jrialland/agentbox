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

    assert reg.select_tools(ask) == [read_file]
    assert set(reg.select_tools(agent)) == {read_file, write_file}


def test_select_tools_filters_by_names():
    reg = ToolRegistry()
    reg.register_native("read_file", read_file, required_flags=("read",))
    reg.register_native("write_file", write_file, required_flags=("write",))

    agent = Mode(name="agent", flags={"write": True})
    assert reg.select_tools(agent, names={"write_file"}) == [write_file]
    assert reg.select_tools(agent, names=set()) == []


async def test_hook_appends_to_string_result():
    async def hook(ctx):
        return f"hooked {ctx.tool_name} {ctx.args['path']}"

    reg = ToolRegistry(hooks=[hook])
    reg.register_native("read_file", read_file, required_flags=("read",))
    tools = reg.select_tools(Mode(name="ask", flags={}))
    assert await tools[0](path="a.txt") == "data\n\nhooked read_file a.txt"
    assert tools[0].__name__ == "read_file"  # ty: ignore[missing-attribute]


async def test_hook_error_is_isolated():
    async def boom(ctx):
        raise RuntimeError("nope")

    reg = ToolRegistry(hooks=[boom])
    reg.register_native("read_file", read_file)
    tools = reg.select_tools(Mode(name="ask", flags={}))
    assert await tools[0](path="a.txt") == "data"


async def test_hook_does_not_modify_non_string_result():
    async def value(path: str) -> dict:
        return {"path": path}

    async def hook(ctx):
        return "extra"

    reg = ToolRegistry(hooks=[hook])
    reg.register_native("value", value)
    tools = reg.select_tools(Mode(name="ask", flags={}))
    assert await tools[0](path="a") == {"path": "a"}

def test_get_native_raw_returns_unwrapped_callable():
    async def original(path: str) -> str:
        return "raw"

    reg = ToolRegistry()
    reg.register_native("read_file", original)

    assert reg.get_native_raw("read_file") is original
    assert reg.get_native_raw("missing") is None


async def test_override_native_preserves_flags_and_runs_hooks_once():
    calls: list[str] = []

    async def hook(ctx):
        calls.append("hook")
        return "hooked"

    async def original(path: str) -> str:
        return "raw"

    async def replacement(path: str) -> str:
        return "new"

    reg = ToolRegistry(hooks=[hook])
    reg.register_native("read_file", original, required_flags=("read",))

    assert reg.override_native("read_file", replacement) is True
    assert reg.get_native_raw("read_file") is replacement
    assert reg.override_native("missing", replacement) is False

    tool = reg.select_tools(Mode(name="ask", flags={}), names={"read_file"})[0]
    assert await tool("a.txt") == "new\n\nhooked"
    assert calls == ["hook"]
