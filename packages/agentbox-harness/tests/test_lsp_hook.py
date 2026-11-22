import pathlib
import sys
import time

from agentbox_harness.lsp.diagnostics import (
    DiagnosticsService,
    make_lsp_diagnostics_tool,
    make_lsp_notify_hook,
)
from agentbox_harness.lsp.hooks import format_diagnostics, make_lsp_hook
from agentbox_harness.lsp.manager import LspManager
from agentbox_harness.lsp.stacks import LspStack
from agentbox_harness.tools.registry import ToolHookContext

FAKE = LspStack(
    "python",
    ("**/*.py",),
    (
        sys.executable,
        str(pathlib.Path(__file__).parent / "fake_lsp_server.py"),
    ),
    ("python",),
    (".py",),
)


async def test_hook_appends_diagnostics(tmp_path):
    manager = LspManager()
    manager.stacks = [FAKE]
    path = tmp_path / "a.py"
    path.write_text("x = 1", encoding="utf-8")
    hook = make_lsp_hook(manager, "s1", str(tmp_path))
    ctx = ToolHookContext(
        tool_name="write_file", args={"path": str(path)}, root=tmp_path, result="ok"
    )
    text = await hook(ctx)
    assert "fake pull error" in text
    assert manager.active_for_session("s1")[0]["stack"] == "python"
    await manager.shutdown()


async def test_hook_skips_non_code(tmp_path):
    manager = LspManager()
    path = tmp_path / "notes.txt"
    path.write_text("x", encoding="utf-8")
    hook = make_lsp_hook(manager, "s1", str(tmp_path))
    ctx = ToolHookContext(
        tool_name="write_file", args={"path": str(path)}, root=tmp_path, result="ok"
    )
    assert await hook(ctx) is None


async def test_hook_clean_file_returns_none(tmp_path):
    manager = LspManager()
    manager.stacks = []
    path = tmp_path / "a.py"
    path.write_text("x", encoding="utf-8")
    hook = make_lsp_hook(manager, "s1", str(tmp_path))
    ctx = ToolHookContext(
        tool_name="write_file", args={"path": str(path)}, root=tmp_path, result="ok"
    )
    assert await hook(ctx) is None


async def test_notify_hook_returns_immediately(tmp_path):
    manager = LspManager()
    manager.stacks = [FAKE]
    service = DiagnosticsService(manager)
    path = tmp_path / "a.py"
    path.write_text("x = 1", encoding="utf-8")
    hook = make_lsp_notify_hook(service, "s1", str(tmp_path))
    ctx = ToolHookContext(
        tool_name="write_file", args={"path": str(path)}, root=tmp_path, result="ok"
    )
    started = time.monotonic()
    assert await hook(ctx) is None
    assert time.monotonic() - started < 0.05
    assert path.resolve() in service._queued
    await service.shutdown()
    await manager.shutdown()


async def test_diagnostics_tool_refreshes_file(tmp_path):
    manager = LspManager()
    manager.stacks = [FAKE]
    service = DiagnosticsService(manager)
    path = tmp_path / "a.py"
    path.write_text("x = 1", encoding="utf-8")
    tool = make_lsp_diagnostics_tool(service, "s1", str(tmp_path))
    text = await tool(path=str(path))
    assert "fake pull error" in text
    await service.shutdown()
    await manager.shutdown()


async def test_diagnostics_tool_rejects_outside_path(tmp_path):
    manager = LspManager()
    service = DiagnosticsService(manager)
    tool = make_lsp_diagnostics_tool(service, "s1", str(tmp_path))
    assert await tool(path=str(tmp_path.parent / "outside.py")) == (
        "path is outside the project"
    )
    await service.shutdown()
    await manager.shutdown()


async def test_diagnostics_tool_rejects_bad_severity(tmp_path):
    manager = LspManager()
    service = DiagnosticsService(manager)
    tool = make_lsp_diagnostics_tool(service, "s1", str(tmp_path))
    assert "severity must be" in await tool(severity="nope")
    await service.shutdown()
    await manager.shutdown()


def test_format_caps_and_filters():
    diagnostics = [
        {
            "severity": 1,
            "range": {"start": {"line": 0, "character": 1}},
            "message": f"error {i}",
        }
        for i in range(12)
    ]
    diagnostics.append({"severity": 4, "message": "hint"})
    text = format_diagnostics("a.py", diagnostics)
    assert text is not None
    assert "and 2 more" in text
    assert "hint" not in text
