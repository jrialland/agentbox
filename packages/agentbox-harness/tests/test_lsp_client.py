import pathlib
import sys

from agentbox_harness.lsp.client import LspServer


def command(*args):
    return [
        sys.executable,
        str(pathlib.Path(__file__).parent / "fake_lsp_server.py"),
        *args,
    ]


async def test_pull_diagnostics(tmp_path):
    path = tmp_path / "a.py"
    path.write_text("x = 1", encoding="utf-8")
    server = await LspServer(command(), tmp_path).start()
    try:
        await server.sync_document(str(path), "python")
        result = await server.diagnostics(str(path))
        assert result[0]["message"] == "fake pull error"
        assert server.documents == 1
    finally:
        await server.stop()


async def test_push_fallback(tmp_path):
    path = tmp_path / "a.py"
    path.write_text("x = 1", encoding="utf-8")
    server = await LspServer(command("--push"), tmp_path).start()
    try:
        await server.sync_document(str(path), "python")
        result = await server.diagnostics(str(path))
        assert result[0]["message"] == "fake error"
    finally:
        await server.stop()


async def test_timeout_returns_empty(tmp_path):
    path = tmp_path / "a.py"
    path.write_text("x = 1", encoding="utf-8")
    server = await LspServer(
        command("--no-response"), tmp_path, diagnostics_timeout=0.2
    ).start()
    try:
        await server.sync_document(str(path), "python")
        assert await server.diagnostics(str(path)) == []
    finally:
        await server.stop()
