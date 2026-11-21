import asyncio
import json
import pathlib
import sys
from types import SimpleNamespace

from agentbox_harness.lsp.manager import LspManager
from agentbox_harness.lsp.stacks import LspStack

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
FAKE_TS = LspStack(
    "typescript",
    ("**/*.ts",),
    FAKE.command,
    ("typescript",),
    (".ts",),
)


def _settings(**overrides):
    values = {
        "lsp_enabled": True,
        "lsp_initialize_timeout": 10.0,
        "lsp_diagnostics_timeout": 5.0,
        "lsp_failure_backoff_seconds": 60.0,
        "lsp_servers_json": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_detected_for_project(tmp_path):
    manager = LspManager()
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    assert manager.detected_for_project(str(tmp_path)) == ["python"]


async def test_get_or_start_reuses_and_tracks_active(tmp_path):
    manager = LspManager()
    server = await manager.get_or_start(str(tmp_path), FAKE)
    assert server is not None
    assert await manager.get_or_start(str(tmp_path), FAKE) is server
    manager.record_active("s1", str(tmp_path), FAKE, server)
    active = manager.active_for_session("s1")
    assert active[0]["stack"] == "python"
    assert active[0]["status"] == "running"
    await manager.shutdown()


async def test_failed_server_backs_off(tmp_path):
    manager = LspManager()
    stack = LspStack(
        FAKE.name,
        FAKE.markers,
        ("definitely-not-a-real-command",),
        FAKE.languages,
        FAKE.extensions,
    )
    assert await manager.get_or_start(str(tmp_path), stack) is None
    assert await manager.get_or_start(str(tmp_path), stack) is None


def test_configure_can_disable_lsp():
    manager = LspManager()
    manager.configure(_settings(lsp_enabled=False))
    assert manager.enabled is False


async def test_disabled_manager_does_not_spawn(tmp_path):
    manager = LspManager()
    manager.enabled = False
    assert await manager.get_or_start(str(tmp_path), FAKE) is None


def test_configure_custom_stacks(tmp_path):
    manager = LspManager()
    payload = json.dumps(
        [
            {
                "name": "custom",
                "markers": ["*.custom"],
                "command": ["echo"],
                "languages": ["custom"],
                "extensions": [".custom"],
            }
        ]
    )
    manager.configure(_settings(lsp_servers_json=payload))
    (tmp_path / "x.custom").write_text("x", encoding="utf-8")
    assert manager.detected_for_project(str(tmp_path)) == ["custom"]


async def test_dead_server_is_replaced(tmp_path):
    manager = LspManager()
    first = await manager.get_or_start(str(tmp_path), FAKE)
    assert first is not None and first.process is not None
    first.process.kill()
    await first.process.wait()
    for _ in range(50):
        if first.dead:
            break
        await asyncio.sleep(0.05)
    assert first.dead
    second = await manager.get_or_start(str(tmp_path), FAKE)
    assert second is not None and second is not first
    await manager.shutdown()


async def test_two_stacks_start_two_servers(tmp_path):
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    (tmp_path / "b.ts").write_text("y", encoding="utf-8")
    manager = LspManager()
    manager.stacks = [FAKE, FAKE_TS]
    assert manager.detected_for_project(str(tmp_path)) == ["python", "typescript"]
    py = await manager.get_or_start(str(tmp_path), FAKE)
    ts = await manager.get_or_start(str(tmp_path), FAKE_TS)
    assert py is not None and ts is not None and py is not ts
    manager.record_active("s1", str(tmp_path), FAKE, py)
    manager.record_active("s1", str(tmp_path), FAKE_TS, ts)
    stacks = {entry["stack"] for entry in manager.active_for_session("s1")}
    assert stacks == {"python", "typescript"}
    await manager.shutdown()


async def test_reset_stops_servers(tmp_path):
    manager = LspManager()
    server = await manager.get_or_start(str(tmp_path), FAKE)
    assert server is not None
    manager.record_active("s1", str(tmp_path), FAKE, server)
    await manager.reset()
    assert manager.active_for_session("s1") == []
    assert server.dead


async def test_manager_passes_quiescence_to_server(tmp_path):
    manager = LspManager()
    stack = LspStack(
        "rustlike",
        ("**/*.rs",),
        FAKE.command,
        ("rust",),
        (".rs",),
        pull=False,
        save=True,
        settle=15.0,
        quiescence="server_status",
    )
    server = await manager.get_or_start(str(tmp_path), stack)
    assert server is not None
    assert server.quiescence == "server_status"
    assert server._tracker is not None
    await manager.shutdown()


async def test_manager_default_stack_has_no_tracker(tmp_path):
    manager = LspManager()
    server = await manager.get_or_start(str(tmp_path), FAKE)
    assert server is not None
    assert server.quiescence is None
    assert server._tracker is None
    await manager.shutdown()


def test_configure_custom_stack_quiescence():
    manager = LspManager()
    payload = json.dumps(
        [
            {
                "name": "custom",
                "markers": ["*.custom"],
                "command": ["echo"],
                "languages": ["custom"],
                "extensions": [".custom"],
                "quiescence": "server_status",
            }
        ]
    )
    manager.configure(_settings(lsp_servers_json=payload))
    assert manager.stacks is not None
    assert manager.stacks[0].quiescence == "server_status"
