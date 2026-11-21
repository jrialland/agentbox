# Rust LSP Quiescence Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return Rust LSP diagnostics as soon as rust-analyzer reports quiescence, instead of always waiting the push-mode settle window, while keeping `didSave` diagnostics and leaving other stacks unchanged.

**Architecture:** Add a per-stack `quiescence` field; the Rust default opts into `"server_status"`. A small `ServerStatusTracker` ingests `experimental/serverStatus`; `LspServer.diagnostics()` uses it to return on quiescence, with the existing settle loop as fallback. No new process lifecycle, settings, API, or UI.

**Tech Stack:** Python 3.11, asyncio, loguru, pytest-asyncio (`asyncio_mode = auto`), rust-analyzer LSP.

## Global Constraints

- Run Python commands from the repo root with `uv`.
- Run tests one package per invocation: `uv run pytest packages/agentbox-harness -q`.
- `asyncio_mode = auto`: write `async def test_...` without decorators.
- Ruff: line length 100, target py311; use `from __future__` only if already needed (not required here).
- Pytest timeout is 60 s; do not change it. Use small `settle`/`diagnostics_timeout` in fake-server tests to keep them fast.
- Use `loguru.logger` for logging.
- No new user-facing settings; behavior is configured by the per-stack `quiescence` field.
- Conventional commit messages: `feat(harness): ...`, `test(harness): ...`, `docs(roadmap): ...`.
- Do not hand-edit generated API artifacts; this plan changes no API schema.

---

## File Structure

- **Create** `packages/agentbox-harness/src/agentbox_harness/lsp/quiescence.py` — `ServerStatusTracker` (capabilities, state, waiter wake-up).
- **Create** `packages/agentbox-harness/tests/test_lsp_quiescence.py` — tracker unit tests.
- **Modify** `packages/agentbox-harness/src/agentbox_harness/lsp/client.py` — accept `quiescence`, advertise capability, ingest status, quiescence-aware wait, per-path publish counts, extracted settle helper.
- **Modify** `packages/agentbox-harness/src/agentbox_harness/lsp/stacks.py` — `LspStack.quiescence`, Rust default.
- **Modify** `packages/agentbox-harness/src/agentbox_harness/lsp/manager.py` — pass `quiescence`.
- **Modify** `packages/agentbox-harness/tests/fake_lsp_server.py` — `--server-status` modes.
- **Modify** `packages/agentbox-harness/tests/test_lsp_client.py` — capability/ingestion/wait tests.
- **Modify** `packages/agentbox-harness/tests/test_lsp_manager.py` — wiring tests.
- **Modify** `packages/agentbox-harness/tests/test_lsp_detection.py` — default-stack assertions.
- **Modify** `packages/agentbox-harness/tests/test_lsp_real.py` — rust-analyzer timing test.
- **Modify** `docs/ROADMAP.md`, `docs/superpowers/specs/2026-11-19-lsp-diagnostics-design.md` — roadmap/spec pointer.

---

## Task 1: ServerStatusTracker

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/lsp/quiescence.py`
- Test: `packages/agentbox-harness/tests/test_lsp_quiescence.py`

**Interfaces:**
- Produces:
  - `ServerStatusTracker` dataclass with `health: str | None`, `quiescent: bool | None`, `seq: int`, `busy_seq: int`, `waiters: set[asyncio.Event]`.
  - `ServerStatusTracker.client_capabilities() -> dict`
  - `ServerStatusTracker.handle(params: dict) -> None`

- [ ] **Step 1: Write the failing tests**

Create `packages/agentbox-harness/tests/test_lsp_quiescence.py`:

```python
import asyncio

from agentbox_harness.lsp.quiescence import ServerStatusTracker


def test_client_capabilities():
    tracker = ServerStatusTracker()
    assert tracker.client_capabilities() == {
        "experimental": {"serverStatusNotification": True}
    }


def test_handle_updates_state_and_busy_counter():
    tracker = ServerStatusTracker()
    tracker.handle({"health": "ok", "quiescent": False})
    assert tracker.health == "ok"
    assert tracker.quiescent is False
    assert tracker.seq == 1
    assert tracker.busy_seq == 1
    tracker.handle({"health": "ok", "quiescent": True})
    assert tracker.quiescent is True
    assert tracker.seq == 2
    assert tracker.busy_seq == 1


def test_handle_records_health_and_message_without_raising():
    tracker = ServerStatusTracker()
    tracker.handle({"health": "warning", "quiescent": True, "message": "loading"})
    assert tracker.health == "warning"
    assert tracker.quiescent is True


def test_handle_wakes_waiters():
    tracker = ServerStatusTracker()
    event = asyncio.Event()
    tracker.waiters.add(event)
    tracker.handle({"health": "ok", "quiescent": True})
    assert event.is_set()
```

(Keep `import asyncio` for `asyncio.Event`; the test itself is synchronous.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_quiescence.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'agentbox_harness.lsp.quiescence'`.

- [ ] **Step 3: Write the implementation**

Create `packages/agentbox-harness/src/agentbox_harness/lsp/quiescence.py`:

```python
import asyncio
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class ServerStatusTracker:
    health: str | None = None
    quiescent: bool | None = None
    seq: int = 0
    busy_seq: int = 0
    waiters: set[asyncio.Event] = field(default_factory=set)

    def client_capabilities(self) -> dict:
        return {"experimental": {"serverStatusNotification": True}}

    def handle(self, params: dict) -> None:
        self.health = params.get("health")
        self.quiescent = bool(params.get("quiescent"))
        self.seq += 1
        if self.quiescent is False:
            self.busy_seq += 1
        logger.debug(
            "lsp server status health={} quiescent={}",
            self.health,
            self.quiescent,
        )
        if self.health not in (None, "ok"):
            logger.warning(
                "lsp server health={} message={}",
                self.health,
                params.get("message"),
            )
        for waiter in self.waiters:
            waiter.set()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_quiescence.py -q`

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/lsp/quiescence.py packages/agentbox-harness/tests/test_lsp_quiescence.py
git commit -m "feat(harness): add LSP server status tracker"
```

---

## Task 2: Advertise capability and ingest `experimental/serverStatus`

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/client.py:26-85` (constructor/capabilities), `:159-192` (reader loop)
- Modify: `packages/agentbox-harness/tests/fake_lsp_server.py`
- Test: `packages/agentbox-harness/tests/test_lsp_client.py`

**Interfaces:**
- Consumes: `ServerStatusTracker` from Task 1.
- Produces:
  - `LspServer(..., quiescence: str | None = None)`
  - `LspServer.quiescence: str | None`
  - `LspServer._tracker: ServerStatusTracker | None`
  - Fake server flags `--server-status`, `--clean`, `--error`, `--stale`, `--busy`, `--busy-then-quiet`.

- [ ] **Step 1: Write the failing tests**

Append to `packages/agentbox-harness/tests/test_lsp_client.py` (and add `import asyncio` at the top):

```python
import asyncio
```

```python
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
```

Note: the fake server only emits status when the client advertised
`experimental.serverStatusNotification`, so `test_advertises_and_ingests_server_status`
fails until the capability is sent.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_client.py -q`

Expected: FAIL — `LspServer.__init__() got an unexpected keyword argument 'quiescence'` (or tracker missing).

- [ ] **Step 3: Add the fake server status modes**

Replace the entire `main()` in `packages/agentbox-harness/tests/fake_lsp_server.py` with the version below, and add `import time` next to `import sys`:

```python
def main():
    push = "--push" in sys.argv or "--server-status" in sys.argv
    server_status = "--server-status" in sys.argv
    no_response = "--no-response" in sys.argv
    clean = "--clean" in sys.argv
    error = "--error" in sys.argv
    stale = "--stale" in sys.argv
    busy = "--busy" in sys.argv
    busy_then_quiet = "--busy-then-quiet" in sys.argv
    status_enabled = False

    def send_status(quiescent):
        send(
            {
                "jsonrpc": "2.0",
                "method": "experimental/serverStatus",
                "params": {"health": "ok", "quiescent": quiescent},
            }
        )

    def publish(uri, diagnostics):
        send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/publishDiagnostics",
                "params": {"uri": uri, "diagnostics": diagnostics},
            }
        )

    error_diagnostic = {
        "range": {"start": {"line": 0, "character": 0}},
        "severity": 1,
        "message": "fake error",
        "source": "fake",
    }

    while True:
        message = read_message()
        if message is None:
            break
        method = message.get("method")
        if method == "initialize":
            capability = (
                message.get("params", {})
                .get("capabilities", {})
                .get("experimental", {})
                .get("serverStatusNotification")
            )
            status_enabled = bool(server_status and capability)
            send(
                {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": {
                        "capabilities": {} if push else {"diagnosticProvider": {}}
                    },
                }
            )
            if status_enabled:
                send_status(True)
        elif method == "textDocument/didOpen":
            if push and not server_status:
                publish(
                    message["params"]["textDocument"]["uri"],
                    [error_diagnostic],
                )
        elif method == "textDocument/didSave":
            if not status_enabled:
                continue
            uri = message["params"]["textDocument"]["uri"]
            if not stale:
                send_status(False)
            if busy:
                publish(uri, [error_diagnostic])
                continue
            if busy_then_quiet:
                time.sleep(0.2)
                send_status(True)
                continue
            if error:
                publish(uri, [error_diagnostic])
            else:
                publish(uri, [])
            if not stale:
                send_status(True)
        elif method == "textDocument/diagnostic":
            if no_response:
                continue
            send(
                {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": {
                        "items": [
                            {
                                "range": {"start": {"line": 2, "character": 3}},
                                "severity": 1,
                                "message": "fake pull error",
                                "source": "fake",
                            }
                        ]
                    },
                }
            )
        elif method == "shutdown":
            send({"jsonrpc": "2.0", "id": message["id"], "result": None})
        elif method == "exit":
            break
```

The flags `--clean` and `--error` select the payload; `--stale` skips the
non-quiescent phase; `--busy` never reports quiescent; `--busy-then-quiet`
delays the final quiescent status by 0.2 s.

- [ ] **Step 4: Wire the tracker into `LspServer`**

In `packages/agentbox-harness/src/agentbox_harness/lsp/client.py`, add the import:

```python
from agentbox_harness.lsp.quiescence import ServerStatusTracker
```

Extend `__init__` (keep the existing parameters, add `quiescence` after `settle`):

```python
    def __init__(
        self,
        command,
        root,
        *,
        pull=True,
        settle=3.0,
        quiescence: str | None = None,
        initialize_timeout=10.0,
        diagnostics_timeout=5.0,
    ):
        self.command = list(command)
        self.root = pathlib.Path(root)
        self.pull = pull
        self.settle = settle
        self.quiescence = quiescence
        self.initialize_timeout = initialize_timeout
        self.diagnostics_timeout = diagnostics_timeout
        self.process = None
        self._reader = None
        self._pending = {}
        self._next_id = 0
        self._versions = {}
        self._diagnostics = {}
        self._diagnostic_events = {}
        self._capabilities = {}
        self._tracker = (
            ServerStatusTracker() if quiescence == "server_status" else None
        )
        self.dead = False
        self._write_lock = asyncio.Lock()
```

In `start()`, merge the tracker capabilities:

```python
        capabilities: dict = {"textDocument": {"publishDiagnostics": {}}}
        if self.pull:
            capabilities["textDocument"]["diagnostic"] = {}
        if self._tracker is not None:
            capabilities.update(self._tracker.client_capabilities())
```

In `_read_loop`, add a branch before the `window/logMessage` branch:

```python
                elif message.get("method") == "experimental/serverStatus":
                    if self._tracker is not None:
                        self._tracker.handle(message.get("params", {}))
                elif message.get("method") in (
                    "window/logMessage",
                    "window/showMessage",
                ):
                    logger.debug("lsp notification {}", message.get("params", {}))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_client.py -q`

Expected: all tests pass (existing 5 plus the 2 new ones).

- [ ] **Step 6: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/lsp/client.py packages/agentbox-harness/tests/fake_lsp_server.py packages/agentbox-harness/tests/test_lsp_client.py
git commit -m "feat(harness): ingest rust-analyzer server status notifications"
```

---

## Task 3: Quiescence-aware diagnostics wait with settle fallback

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/client.py:174-264`
- Test: `packages/agentbox-harness/tests/test_lsp_client.py`

**Interfaces:**
- Consumes: `LspServer._tracker`, `ServerStatusTracker.busy_seq`, `ServerStatusTracker.quiescent`, `ServerStatusTracker.waiters`.
- Produces:
  - `LspServer._publish_counts: dict[pathlib.Path, int]`
  - `LspServer._settle_wait(target, grace) -> list[dict]`
  - `LspServer._quiescence_wait(target, grace) -> list[dict]`

- [ ] **Step 1: Write the failing tests**

Append to `packages/agentbox-harness/tests/test_lsp_client.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_client.py -q`

Expected: the new quiescence tests fail (clean write waits the full grace or returns early with the wrong value; `_settle_wait` / `_quiescence_wait` may not exist).

- [ ] **Step 3: Add per-path publish counts**

In `LspServer.__init__`, after `self._diagnostic_events = {}`, add:

```python
        self._publish_counts = {}
```

In the `textDocument/publishDiagnostics` branch of `_read_loop`, after storing diagnostics, add:

```python
                    self._diagnostics[key] = published
                    self._publish_counts[key] = (
                        self._publish_counts.get(key, 0) + 1
                    )
```

- [ ] **Step 4: Replace `diagnostics()` with the dispatcher and helpers**

Replace the existing `diagnostics()` method with:

```python
    async def diagnostics(self, path: str):
        target = pathlib.Path(path).resolve()
        uri = target.as_uri()
        try:
            if self.pull and "diagnosticProvider" in self._capabilities:
                result = await self._request(
                    "textDocument/diagnostic",
                    {"textDocument": {"uri": uri}},
                    timeout=self.diagnostics_timeout,
                )
                return (result or {}).get("items", [])
            grace = min(self.diagnostics_timeout, self.settle)
            if self._tracker is not None and self._tracker.seq > 0:
                return await self._quiescence_wait(target, grace)
            return await self._settle_wait(target, grace)
        except TimeoutError:
            return []

    async def _settle_wait(self, target, grace):
        event = asyncio.Event()
        self._diagnostic_events[target] = event
        last = self._diagnostics.get(target, [])
        if last:
            return last
        loop = asyncio.get_running_loop()
        deadline = loop.time() + grace
        try:
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return last
                try:
                    await asyncio.wait_for(event.wait(), remaining)
                except TimeoutError:
                    return last
                event.clear()
                last = self._diagnostics.get(target, [])
                if last:
                    return last
        finally:
            self._diagnostic_events.pop(target, None)

    async def _quiescence_wait(self, target, grace):
        tracker = self._tracker
        assert tracker is not None
        busy_seq_at_start = tracker.busy_seq
        publish_at_start = self._publish_counts.get(target, 0)
        event = asyncio.Event()
        self._diagnostic_events[target] = event
        tracker.waiters.add(event)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + grace
        try:
            while True:
                settled = tracker.quiescent is True and (
                    self._publish_counts.get(target, 0) > publish_at_start
                    or tracker.busy_seq > busy_seq_at_start
                )
                if settled:
                    return self._diagnostics.get(target, [])
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return self._diagnostics.get(target, [])
                event.clear()
                try:
                    await asyncio.wait_for(event.wait(), remaining)
                except TimeoutError:
                    return self._diagnostics.get(target, [])
        finally:
            self._diagnostic_events.pop(target, None)
            tracker.waiters.discard(event)
```

- [ ] **Step 5: Run the client tests to verify they pass**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_client.py -q`

Expected: all tests pass, including the pre-existing pull/push/timeout/stop tests.

- [ ] **Step 6: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/lsp/client.py packages/agentbox-harness/tests/test_lsp_client.py
git commit -m "feat(harness): return Rust diagnostics on LSP quiescence"
```

---

## Task 4: Per-stack configuration and manager wiring

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/stacks.py:5-47`
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/manager.py:52-59`
- Test: `packages/agentbox-harness/tests/test_lsp_detection.py`, `packages/agentbox-harness/tests/test_lsp_manager.py`

**Interfaces:**
- Consumes: `LspServer(quiescence=...)` from Task 2.
- Produces: `LspStack.quiescence: str | None`; Rust default `"server_status"`.

- [ ] **Step 1: Write the failing tests**

Append to `packages/agentbox-harness/tests/test_lsp_detection.py`:

```python
def test_rust_default_uses_server_status_quiescence():
    rust = next(stack for stack in DEFAULT_LSP_SERVERS if stack.name == "rust")
    assert rust.quiescence == "server_status"
    assert rust.pull is False
    assert rust.save is True
    assert rust.settle == 15.0


def test_other_default_stacks_have_no_quiescence():
    others = [stack for stack in DEFAULT_LSP_SERVERS if stack.name != "rust"]
    assert all(stack.quiescence is None for stack in others)
```

Append to `packages/agentbox-harness/tests/test_lsp_manager.py`:

```python
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
    assert manager.stacks[0].quiescence == "server_status"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_detection.py packages/agentbox-harness/tests/test_lsp_manager.py -q`

Expected: FAIL — `AttributeError: 'LspStack' object has no attribute 'quiescence'` (or the manager does not pass it).

- [ ] **Step 3: Add the stack field and Rust default**

In `packages/agentbox-harness/src/agentbox_harness/lsp/stacks.py`:

```python
    pull: bool = True
    save: bool = False
    settle: float = 3.0
    quiescence: str | None = None
```

Add to the Rust entry:

```python
        pull=False,
        save=True,
        settle=15.0,
        quiescence="server_status",
```

- [ ] **Step 4: Pass it through the manager**

In `packages/agentbox-harness/src/agentbox_harness/lsp/manager.py`, add `quiescence=stack.quiescence` to the `LspServer(...)` call:

```python
            server = LspServer(
                stack.command,
                project_root,
                pull=stack.pull,
                settle=stack.settle,
                quiescence=stack.quiescence,
                initialize_timeout=self.initialize_timeout,
                diagnostics_timeout=self.diagnostics_timeout,
            )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_detection.py -q`

Then: `uv run pytest packages/agentbox-harness/tests/test_lsp_manager.py -q`

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/lsp/stacks.py packages/agentbox-harness/src/agentbox_harness/lsp/manager.py packages/agentbox-harness/tests/test_lsp_detection.py packages/agentbox-harness/tests/test_lsp_manager.py
git commit -m "feat(harness): enable server-status quiescence for rust stack"
```

---

## Task 5: Real rust-analyzer timing test

**Files:**
- Modify: `packages/agentbox-harness/tests/test_lsp_real.py`
- Test: `packages/agentbox-harness/tests/test_lsp_real.py`

**Interfaces:**
- Consumes: Rust stack default from Task 4 and the quiescence wait from Task 3.
- Produces: no production interfaces.

- [ ] **Step 1: Write the failing test**

Add `import time` to `packages/agentbox-harness/tests/test_lsp_real.py` and append:

```python
@pytest.mark.skipif(
    not _available("rust-analyzer") or shutil.which("cargo") is None,
    reason="rust-analyzer/cargo not installed",
)
async def test_rust_analyzer_clean_write_is_fast(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        "[package]\nname = 'x'\nversion = '0.1.0'\nedition = '2021'\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    main = tmp_path / "src" / "main.rs"
    manager = LspManager()
    manager.initialize_timeout = 60.0
    manager.diagnostics_timeout = 10.0
    hook = make_lsp_hook(manager, "real", str(tmp_path))
    try:
        main.write_text(
            'fn main() { let x: i32 = 1; println!("{}", x); }\n',
            encoding="utf-8",
        )
        await hook(
            ToolHookContext(
                tool_name="write_file",
                args={"path": str(main)},
                root=tmp_path,
                result="ok",
            )
        )
        server = next(iter(manager._servers.values()), None)
        assert server is not None
        if server._tracker is None or server._tracker.seq == 0:
            pytest.skip("rust-analyzer did not send experimental/serverStatus")
        main.write_text(
            'fn main() { let x: i32 = 2; println!("{}", x); }\n',
            encoding="utf-8",
        )
        started = time.perf_counter()
        text = await hook(
            ToolHookContext(
                tool_name="write_file",
                args={"path": str(main)},
                root=tmp_path,
                result="ok",
            )
        )
        elapsed = time.perf_counter() - started
        assert text is None
        assert elapsed < 2.0
    finally:
        await manager.shutdown()
```

The first write warms up the server; only the second write is timed.

- [ ] **Step 2: Run the test to verify it fails (or skips)**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_real.py::test_rust_analyzer_clean_write_is_fast -q`

Expected: PASS if rust-analyzer/cargo are installed (this depends on Tasks 1–4 being complete); SKIPPED if the tools are absent. If it fails with a long elapsed time, confirm Tasks 3–4 are applied.

- [ ] **Step 3: Run the full real-server file**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_real.py -q`

Expected: all available tests pass; unavailable ones skip.

- [ ] **Step 4: Commit**

```bash
git add packages/agentbox-harness/tests/test_lsp_real.py
git commit -m "test(harness): assert rust-analyzer clean writes return fast"
```

---

## Task 6: Docs, roadmap, and final checks

**Files:**
- Modify: `docs/ROADMAP.md`
- Modify: `docs/superpowers/specs/2026-11-19-lsp-diagnostics-design.md`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Update the roadmap**

In `docs/ROADMAP.md`:

1. Add D19 to the completed-cycle sentence (the paragraph before the
   sub-project history):

```markdown
The visual direction is **technical command center with hacker/computer-culture pop** (pixel display type, phosphor palette, subtle CRT accents). **UX-1 through UX-4, D19, D20, and D21 are complete** - specs `superpowers/specs/2026-11-20-ux-1-design-system-design.md`, `superpowers/specs/2026-11-21-ux-2-chat-surface-design.md`, `superpowers/specs/2026-11-21-ux-3-contextual-help-structured-editors-design.md`, `superpowers/specs/2026-11-21-ux-4-data-integrity-design.md`, `superpowers/specs/2026-11-21-rust-lsp-quiescence-design.md`, `superpowers/specs/2026-11-21-agents-md-project-instructions-design.md`, and `superpowers/specs/2026-11-21-grep-content-search-design.md`; plans `superpowers/plans/2026-11-20-ux-1-design-system.md`, `superpowers/plans/2026-11-21-ux-2-chat-surface.md`, `superpowers/plans/2026-11-21-ux-3-contextual-help-structured-editors.md`, `superpowers/plans/2026-11-21-ux-4-data-integrity.md`, `superpowers/plans/2026-11-21-rust-lsp-quiescence.md`, `superpowers/plans/2026-11-21-agents-md-project-instructions.md`, and `superpowers/plans/2026-11-21-grep-content-search.md`. The next cycle is not yet scheduled.
```

2. Add a row to the sub-project history table after #35:

```markdown
| 36 | D19 Rust LSP quiescence readiness | `specs/2026-11-21-rust-lsp-quiescence-design.md` | `plans/2026-11-21-rust-lsp-quiescence.md` |
```

3. Delete the D19 row from the deferred backlog.

- [ ] **Step 2: Add the pointer in the original LSP spec**

In `docs/superpowers/specs/2026-11-19-lsp-diagnostics-design.md`, extend the Rust note (after the existing `> The Rust server uses ...` blockquote) with:

```markdown
> Readiness timing for Rust is refined by D19:
> `2026-11-21-rust-lsp-quiescence-design.md` (return on
> `experimental/serverStatus` quiescence; settle remains the fallback).
```

- [ ] **Step 3: Run the full harness suite**

Run: `uv run pytest packages/agentbox-harness -q`

Expected: all pass.

- [ ] **Step 4: Run lint and type checks**

Run: `uv run ruff check --fix packages`

Then: `uv run ty check packages`

Expected: no errors. Fix any issues and re-run.

- [ ] **Step 5: Commit**

```bash
git add docs/ROADMAP.md docs/superpowers/specs/2026-11-19-lsp-diagnostics-design.md
git commit -m "docs(roadmap): mark D19 Rust LSP quiescence complete"
```

---

## Self-Review

**Spec coverage:**
- Goal / return at quiescence: Task 3 (`_quiescence_wait`).
- Stack-configured strategy, Rust default: Task 4.
- Capability advertisement: Task 2.
- Status ingestion, health logging, waiters: Tasks 1–2.
- Fallback to settle: Task 3 (`_settle_wait`, `tracker.seq == 0` branch).
- Per-path publish counter + `busy_seq` guard: Task 3.
- `didSave` retained: unchanged in `hooks.py`; Task 5 exercises it.
- Tests (fake + real timing): Tasks 2, 3, 5.
- Roadmap/spec pointer: Task 6.
- No API/UI/settings changes: no tasks touch them.

**Placeholder scan:** no TBD/TODO; every step has runnable code or exact edits.

**Type consistency:** `quiescence: str | None` is used consistently in `LspStack`, `LspServer`, and the manager. Tracker names (`seq`, `busy_seq`, `quiescent`, `waiters`, `handle`, `client_capabilities`) match across tasks. `_publish_counts`, `_settle_wait`, `_quiescence_wait` are defined in Task 3 and referenced only there.
