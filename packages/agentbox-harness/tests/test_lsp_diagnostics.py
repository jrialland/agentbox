import asyncio
import pathlib
import sys
import time
from dataclasses import replace

from agentbox_harness.lsp.diagnostics import (
    DiagnosticsService,
    DiagnosticsSnapshot,
    make_lsp_diagnostics_tool,
    make_lsp_notify_hook,
)
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


async def test_note_write_returns_immediately_and_analyses(tmp_path):
    manager = LspManager()
    manager.stacks = [FAKE]
    service = DiagnosticsService(manager, max_wait=5.0)
    path = tmp_path / "a.py"
    path.write_text("x = 1", encoding="utf-8")
    started = time.monotonic()
    service.note_write("s1", str(tmp_path), str(path))
    assert time.monotonic() - started < 0.05
    snapshot = await service.refresh(
        "s1", str(tmp_path), str(path), timeout=5.0
    )
    assert snapshot.state == "ready"
    assert snapshot.diagnostics[0]["message"] == "fake pull error"
    await service.shutdown()
    await manager.shutdown()


async def test_rapid_writes_coalesce(tmp_path):
    manager = LspManager()
    manager.stacks = [FAKE]
    service = DiagnosticsService(manager)
    path = tmp_path / "a.py"
    path.write_text("x = 1", encoding="utf-8")
    for _ in range(10):
        service.note_write("s1", str(tmp_path), str(path))
    await asyncio.sleep(0.3)
    assert service._analysis_count == 1
    await service.shutdown()
    await manager.shutdown()


def _snapshot(generation, diagnostics):
    return DiagnosticsSnapshot(
        "a.py",
        "python",
        "/repo",
        generation,
        "ready",
        tuple(diagnostics),
    )


async def test_reminder_only_errors_and_dedupes():
    service = DiagnosticsService(manager=LspManager())
    path = pathlib.Path("a.py")
    service._touched["s1"] = {path}
    service._snapshots[path] = _snapshot(
        2,
        [
            {
                "severity": 1,
                "range": {"start": {"line": 3, "character": 7}},
                "message": "boom",
                "source": "fake",
            }
        ],
    )
    first = await service.reminder("s1")
    assert first is not None
    assert "boom" in first
    assert "<lsp_diagnostics>" in first
    assert await service.reminder("s1") is None


async def test_reminder_ignores_warnings():
    service = DiagnosticsService(manager=LspManager())
    path = pathlib.Path("a.py")
    service._touched["s1"] = {path}
    service._snapshots[path] = _snapshot(
        1,
        [
            {
                "severity": 2,
                "range": {"start": {"line": 1, "character": 1}},
                "message": "warning only",
            }
        ],
    )
    assert await service.reminder("s1") is None


async def test_notify_then_tool_then_reminder(tmp_path):
    manager = LspManager()
    manager.stacks = [FAKE]
    service = DiagnosticsService(manager, max_wait=5.0)
    path = tmp_path / "a.py"
    path.write_text("x = 1", encoding="utf-8")
    hook = make_lsp_notify_hook(service, "s1", str(tmp_path))
    tool = make_lsp_diagnostics_tool(service, "s1", str(tmp_path))
    ctx = ToolHookContext(
        tool_name="write_file",
        args={"path": str(path)},
        root=tmp_path,
        result="ok",
    )
    assert await hook(ctx) is None
    text = await tool(path=str(path))
    assert "fake pull error" in text
    reminder = await service.reminder("s1")
    assert reminder is not None
    assert "fake pull error" in reminder
    await service.shutdown()
    await manager.shutdown()


async def test_unavailable_server_produces_error_snapshot(tmp_path):
    manager = LspManager()
    manager.stacks = [replace(FAKE, command=("definitely-not-a-real-command",))]
    service = DiagnosticsService(manager)
    path = tmp_path / "a.py"
    path.write_text("x = 1", encoding="utf-8")
    service.note_write("s1", str(tmp_path), str(path))
    snapshot = await service.refresh(
        "s1", str(tmp_path), str(path), timeout=2.0
    )
    assert snapshot.state == "error"
    await service.shutdown()
    await manager.shutdown()
