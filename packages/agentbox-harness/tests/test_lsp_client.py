import asyncio
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


async def test_stop_shuts_down_process(tmp_path):
    server = await LspServer(command(), tmp_path).start()
    process = server.process
    assert process is not None
    await server.stop()
    assert server.dead
    assert process.returncode is not None


async def test_unknown_server_request_returns_method_not_found(tmp_path):
    server = LspServer(command(), tmp_path)
    sent = []

    async def fake_send(message):
        sent.append(message)

    server._send = fake_send
    await server._handle_server_request({"id": 9, "method": "unknown/request"})
    assert sent[0]["error"]["code"] == -32601


async def test_advertises_and_ingests_server_status(tmp_path):
    server = await LspServer(
        command("--server-status", "--clean"),
        tmp_path,
        quiescence="server_status",
    ).start()
    try:
        for _ in range(100):
            if server._tracker is not None and server._tracker.seq > 0:
                break
            await asyncio.sleep(0.02)
        assert server._tracker is not None
        assert server._tracker.quiescent is True
        assert server._tracker.health == "ok"
    finally:
        await server.stop()


async def test_no_tracker_without_quiescence(tmp_path):
    server = await LspServer(
        command("--server-status", "--clean"), tmp_path
    ).start()
    try:
        assert server._tracker is None
    finally:
        await server.stop()


def _elapsed(started):
    return asyncio.get_running_loop().time() - started


async def _quiescence_server(tmp_path, *args, settle=5.0, timeout=5.0):
    server = await LspServer(
        command("--server-status", *args),
        tmp_path,
        quiescence="server_status",
        settle=settle,
        diagnostics_timeout=timeout,
    ).start()
    for _ in range(100):
        if server._tracker is not None and server._tracker.seq > 0:
            break
        await asyncio.sleep(0.01)
    return server


async def test_quiescence_clean_returns_fast(tmp_path):
    path = tmp_path / "a.rs"
    path.write_text("fn main() {}", encoding="utf-8")
    server = await _quiescence_server(tmp_path, "--clean")
    try:
        await server.sync_document(str(path), "rust")
        await server.save_document(str(path))
        started = asyncio.get_running_loop().time()
        result = await server.diagnostics(str(path))
        assert result == []
        assert _elapsed(started) < 2.0
    finally:
        await server.stop()


async def test_quiescence_error_returns_diagnostics(tmp_path):
    path = tmp_path / "a.rs"
    path.write_text("fn main() {}", encoding="utf-8")
    server = await _quiescence_server(tmp_path, "--error")
    try:
        await server.sync_document(str(path), "rust")
        await server.save_document(str(path))
        result = await server.diagnostics(str(path))
        assert result[0]["message"] == "fake error"
    finally:
        await server.stop()


async def test_quiescence_publish_while_quiescent_returns_fast(tmp_path):
    path = tmp_path / "a.rs"
    path.write_text("fn main() {}", encoding="utf-8")
    server = await _quiescence_server(tmp_path, "--stale", "--error")
    try:
        await server.sync_document(str(path), "rust")
        await server.save_document(str(path))
        started = asyncio.get_running_loop().time()
        result = await server.diagnostics(str(path))
        assert result[0]["message"] == "fake error"
        assert _elapsed(started) < 2.0
    finally:
        await server.stop()


async def test_quiescence_waits_for_quiet(tmp_path):
    path = tmp_path / "a.rs"
    path.write_text("fn main() {}", encoding="utf-8")
    server = await _quiescence_server(tmp_path, "--busy-then-quiet")
    try:
        await server.sync_document(str(path), "rust")
        await server.save_document(str(path))
        started = asyncio.get_running_loop().time()
        result = await server.diagnostics(str(path))
        elapsed = _elapsed(started)
        assert result == []
        assert elapsed >= 0.15
        assert elapsed < 2.0
    finally:
        await server.stop()


async def test_quiescence_busy_timeout_returns_latest(tmp_path):
    path = tmp_path / "a.rs"
    path.write_text("fn main() {}", encoding="utf-8")
    server = await _quiescence_server(tmp_path, "--busy", settle=0.5, timeout=0.5)
    try:
        await server.sync_document(str(path), "rust")
        await server.save_document(str(path))
        result = await server.diagnostics(str(path))
        assert result[0]["message"] == "fake error"
    finally:
        await server.stop()


async def test_quiescence_without_status_falls_back_to_settle(tmp_path):
    path = tmp_path / "a.py"
    path.write_text("x = 1", encoding="utf-8")
    server = await LspServer(
        command("--push"),
        tmp_path,
        quiescence="server_status",
        settle=1.0,
        diagnostics_timeout=1.0,
    ).start()
    try:
        await server.sync_document(str(path), "python")
        result = await server.diagnostics(str(path))
        assert result[0]["message"] == "fake error"
    finally:
        await server.stop()
