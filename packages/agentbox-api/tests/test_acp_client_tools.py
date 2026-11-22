import pathlib

import pytest
from acp import schema as s

from agentbox_api.acp_client_tools import (
    AcpClientCapabilities,
    AcpClientTools,
    install_acp_client_tools,
)
from agentbox_harness.spec import AgentSpec, Mode, ModelBinding, NativeToolBinding
from agentbox_harness.tools.filesystem import FileEdit
from agentbox_harness.tools.registry import ToolRegistry


class FakeClient:
    def __init__(self):
        self.reads = []
        self.writes = []

    async def read_text_file(self, session_id, path, line=None, limit=None, **kwargs):
        self.reads.append((session_id, path))
        return s.ReadTextFileResponse(content=pathlib.Path(path).read_text())

    async def write_text_file(self, session_id, path, content, **kwargs):
        self.writes.append((session_id, path, content))
        pathlib.Path(path).write_text(content)
        return None


async def server_read(path, head=None, tail=None):
    return "server read"


async def server_write(path, content):
    return "server write"


async def server_edit(path, edits, dry_run=False):
    return "server edit"


async def server_append(path, content):
    return "server append"


async def server_copy(source, destination):
    return "server copy"


async def server_read_multiple(paths):
    return "server multiple"


def _registry():
    reg = ToolRegistry()
    reg.register_native("read_text_file", server_read, required_flags=("read",))
    reg.register_native("read_file", server_read, required_flags=("read",))
    reg.register_native(
        "read_multiple_files", server_read_multiple, required_flags=("read",)
    )
    reg.register_native("write_file", server_write, required_flags=("write",))
    reg.register_native("append_file", server_append, required_flags=("write",))
    reg.register_native("edit_file", server_edit, required_flags=("write",))
    reg.register_native("copy_file", server_copy, required_flags=("write",))
    return reg


def _spec(names):
    return AgentSpec(
        name="coder",
        description="d",
        instructions="i",
        tool_bindings=[NativeToolBinding(name=name) for name in names],
        model_binding=ModelBinding(model="test", provider="test"),
    )


def _tools(tmp_path, client, caps):
    return AcpClientTools(
        client=client,
        session_id="s1",
        project_root=str(tmp_path),
        extra_roots=[],
        capabilities=caps,
    )


def _tool(reg, name):
    return reg.select_tools(Mode(name="agent", flags={"write": True}), names={name})[0]


async def test_no_capabilities_leaves_server_tools(tmp_path):
    reg = _registry()
    install_acp_client_tools(
        reg,
        _spec(["read_text_file", "write_file"]),
        _tools(tmp_path, FakeClient(), AcpClientCapabilities()),
    )
    assert await _tool(reg, "read_text_file")("a.txt") == "server read"
    assert await _tool(reg, "write_file")("a.txt", "x") == "server write"


async def test_read_routes_head_and_tail(tmp_path):
    (tmp_path / "a.txt").write_text("a\nb\nc\n")
    reg = _registry()
    client = FakeClient()
    install_acp_client_tools(
        reg,
        _spec(["read_text_file"]),
        _tools(tmp_path, client, AcpClientCapabilities(read_text_file=True)),
    )
    tool = _tool(reg, "read_text_file")
    assert await tool("a.txt", head=2) == "a\nb"
    assert await tool("a.txt", tail=2) == "b\nc"
    assert await tool("a.txt") == "a\nb\nc\n"
    assert client.reads


async def test_write_and_composed_tools_use_client(tmp_path):
    (tmp_path / "a.txt").write_text("old")
    reg = _registry()
    client = FakeClient()
    install_acp_client_tools(
        reg,
        _spec(["write_file", "append_file", "edit_file", "copy_file"]),
        _tools(
            tmp_path,
            client,
            AcpClientCapabilities(read_text_file=True, write_text_file=True),
        ),
    )

    assert await _tool(reg, "write_file")("b.txt", "new") == "Wrote 3 bytes to b.txt"
    assert await _tool(reg, "append_file")("a.txt", "!") == "Appended 1 bytes to a.txt"
    assert (tmp_path / "a.txt").read_text() == "old!"

    assert (
        await _tool(reg, "edit_file")("a.txt", [FileEdit("old", "NEW")])
        == "Edited a.txt"
    )
    assert (tmp_path / "a.txt").read_text() == "NEW!"

    diff = await _tool(reg, "edit_file")(
        "a.txt", [FileEdit("NEW", "NEWER")], dry_run=True
    )
    assert "+NEWER" in diff
    assert (tmp_path / "a.txt").read_text() == "NEW!"

    assert (
        await _tool(reg, "copy_file")("a.txt", "c.txt")
        == "Copied a.txt to c.txt"
    )
    assert (tmp_path / "c.txt").read_text() == "NEW!"
    assert client.writes


async def test_outside_root_falls_back_to_server_tool(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside")
    reg = _registry()
    client = FakeClient()
    install_acp_client_tools(
        reg,
        _spec(["read_text_file"]),
        _tools(tmp_path, client, AcpClientCapabilities(read_text_file=True)),
    )
    assert await _tool(reg, "read_text_file")(str(outside)) == "server read"
    assert client.reads == []


async def test_client_error_is_surfaced(tmp_path):
    class BrokenClient(FakeClient):
        async def read_text_file(self, *args, **kwargs):
            raise RuntimeError("client failed")

    reg = _registry()
    install_acp_client_tools(
        reg,
        _spec(["read_text_file"]),
        _tools(tmp_path, BrokenClient(), AcpClientCapabilities(read_text_file=True)),
    )
    with pytest.raises(RuntimeError, match="client failed"):
        await _tool(reg, "read_text_file")("a.txt")
