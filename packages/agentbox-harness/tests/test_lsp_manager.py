import pathlib
import sys

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
