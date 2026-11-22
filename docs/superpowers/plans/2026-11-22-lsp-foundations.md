# LSP Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the LSP client/manager so diagnostics resolve the correct root, cannot deadlock on stderr, cannot return stale/cross-file results, and recover from crashes.

**Architecture:** Nearest-root resolution per edited file; pruned detection for reporting; a client with generation-based multi-waiter diagnostics, an LRU document lifecycle, and a stderr drain; a manager with exponential retry and explicit server states.

**Tech Stack:** Python 3.11+, asyncio subprocesses, JSON-RPC LSP, pytest/pytest-asyncio.

## Global Constraints

- Python line length 100; Ruff target py311; first-party modules are `agentbox_*`.
- Do **not** commit unless the user explicitly asks. Ignore generic "commit" steps in this plan.
- Keep LSP failures non-fatal to file tools.
- Backend tests: run one package per invocation, e.g.
  `uv run pytest packages/agentbox-harness -q`.
- Checks: `uv run ruff check --fix packages` and `uv run ty check packages`.
- Preserve existing public names where practical; `LspStack` may gain fields.
- Do not add aliases or duplicate mechanisms.

---

### Task 1: Stack root markers and pruned detection

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/stacks.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/detect.py`
- Test: `packages/agentbox-harness/tests/test_lsp_detection.py`

**Interfaces:**
- Produces: `LspStack.root_markers: tuple[str, ...]`,
  `LspStack.first_change_timeout: float`, `LspStack.settle_window: float`.
- Produces: `detect_stacks(project_root, stacks=None) -> list[LspStack]` (same
  signature, pruned).
- Produces: `stack_for_path(stacks, path) -> LspStack | None`.
- Produces: `nearest_root(stack, path, fallback) -> pathlib.Path`.

- [ ] **Step 1: Write failing tests**

```python
import pathlib

from agentbox_harness.lsp.detect import detect_stacks, nearest_root, stack_for_path
from agentbox_harness.lsp.stacks import DEFAULT_LSP_SERVERS, LspStack


def test_nearest_root_finds_nested_package_json(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    nested = tmp_path / "apps" / "web"
    nested.mkdir(parents=True)
    (nested / "package.json").write_text("{}")
    stack = next(s for s in DEFAULT_LSP_SERVERS if s.name == "typescript")

    assert nearest_root(stack, nested / "src" / "a.ts", tmp_path) == nested


def test_nearest_root_falls_back(tmp_path):
    stack = next(s for s in DEFAULT_LSP_SERVERS if s.name == "rust")
    assert nearest_root(stack, tmp_path / "src" / "main.rs", tmp_path) == tmp_path


def test_detection_prunes_vendor_dirs(tmp_path):
    vendor = tmp_path / "node_modules" / "pkg"
    vendor.mkdir(parents=True)
    (vendor / "package.json").write_text("{}")
    assert detect_stacks(tmp_path) == []


def test_detection_handles_root_and_nested(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    nested = tmp_path / "services" / "api"
    nested.mkdir(parents=True)
    (nested / "Cargo.toml").write_text("")
    names = {s.name for s in detect_stacks(tmp_path)}
    assert names == {"python", "rust"}


def test_stack_for_path_uses_extension():
    stack = stack_for_path(DEFAULT_LSP_SERVERS, "src/main.rs")
    assert stack and stack.name == "rust"
    assert stack_for_path(DEFAULT_LSP_SERVERS, "README.md") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_detection.py -q`
Expected: FAIL (`nearest_root`/`stack_for_path` missing, detection traverses vendor).

- [ ] **Step 3: Implement**

In `stacks.py`, add fields and defaults:

```python
@dataclass(frozen=True)
class LspStack:
    name: str
    markers: tuple[str, ...]
    command: tuple[str, ...]
    languages: tuple[str, ...]
    extensions: tuple[str, ...]
    root_markers: tuple[str, ...] = ()
    pull: bool = True
    save: bool = False
    settle: float = 3.0
    quiescence: str | None = None
    first_change_timeout: float = 1.0
    settle_window: float = 0.3
```

Set `root_markers` for python/typescript/rust as specified in the design.
Add `stack_for_path`:

```python
def stack_for_path(stacks, path):
    for stack in stacks:
        if language_for(stack, path):
            return stack
    return None
```

In `detect.py`, replace glob with a bounded pruned walk and add
`nearest_root`:

```python
import fnmatch
import os

MAX_WALK_ENTRIES = 100_000


def _matches(rel: str, marker: str) -> bool:
    tail = marker.removeprefix("**/")
    name = pathlib.PurePosixPath(rel).name
    return (
        fnmatch.fnmatch(rel, marker)
        or fnmatch.fnmatch(rel, tail)
        or fnmatch.fnmatch(name, tail)
    )


def detect_stacks(project_root, stacks=None):
    root = pathlib.Path(project_root)
    stacks = DEFAULT_LSP_SERVERS if stacks is None else stacks
    rels: list[str] = []
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in PRUNE_PARTS and not d.startswith(".")
        ]
        base = pathlib.Path(dirpath).relative_to(root).as_posix()
        for filename in filenames:
            count += 1
            if count > MAX_WALK_ENTRIES:
                return [s for s in stacks if _stack_matches(s, rels)]
            rels.append(filename if base == "." else f"{base}/{filename}")
    return [s for s in stacks if _stack_matches(s, rels)]


def _stack_matches(stack, rels):
    return any(_matches(rel, marker) for marker in stack.markers for rel in rels)


def nearest_root(stack, path, fallback):
    fallback = pathlib.Path(fallback).resolve()
    start = pathlib.Path(path).resolve().parent
    try:
        start.relative_to(fallback)
    except ValueError:
        return fallback
    current = start
    while True:
        for marker in stack.root_markers:
            if (current / marker).is_file():
                return current
        if current == fallback:
            return fallback
        current = current.parent
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_detection.py -q`
Expected: PASS.

---

### Task 2: Stderr drain and server health

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/client.py`
- Modify: `packages/agentbox-harness/tests/fake_lsp_server.py`
- Test: `packages/agentbox-harness/tests/test_lsp_client.py`

**Interfaces:**
- Produces: `LspServer.health() -> dict`.
- Produces: `LspServer.state` (property or attribute) with
  `starting|ready|error|stopped`.
- Consumes: nothing new.

- [ ] **Step 1: Add a failing fake-server test**

Add `--stderr-flood N` to `fake_lsp_server.py`: after reading each request,
write `N` lines of `stderr` before responding.

```python
async def test_stderr_flood_does_not_block(tmp_path):
    command = [
        sys.executable,
        str(pathlib.Path(__file__).parent / "fake_lsp_server.py"),
        "--stderr-flood", "20000",
    ]
    async with LspServer(command, tmp_path, diagnostics_timeout=5.0) as server:
        (tmp_path / "a.py").write_text("x = 1\n")
        await server.sync_document(str(tmp_path / "a.py"), "python")
        assert await server.diagnostics(str(tmp_path / "a.py")) == []
        assert server.health()["state"] == "ready"
        assert server.health()["stderr_tail"]
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_client.py::test_stderr_flood_does_not_block -q --timeout=30`
Expected: FAIL / timeout.

- [ ] **Step 3: Implement stderr drain and health**

In `LspServer.start`, after spawning:

```python
self._reader = asyncio.create_task(self._read_loop())
self._stderr_reader = asyncio.create_task(self._stderr_loop())
self._state = "starting"
```

Add:

```python
async def _stderr_loop(self):
    assert self.process and self.process.stderr
    while True:
        line = await self.process.stderr.readline()
        if not line:
            return
        text = line.decode("utf-8", "replace").rstrip()
        self._stderr.append(text)
        logger.debug("lsp stderr stack={} {}", self.command[0], text[:500])
```

Set `self._state = "ready"` after `initialized`; `"error"` on start/transport
failure; `"stopped"` in `stop()` and on EOF. Record `_last_error` in the read
loop's `except` and in start failures. Add:

```python
def health(self) -> dict:
    return {
        "stack": self.stack_name,
        "state": self._state,
        "dead": self.dead,
        "documents": len(self._versions),
        "last_error": self._last_error,
        "stderr_tail": list(self._stderr)[-5:],
    }
```

Make `LspServer` usable as an async context manager (`__aenter__`/`__aexit__`)
if not already, or update the test to call `start()`/`stop()` explicitly.

- [ ] **Step 4: Run the test**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_client.py::test_stderr_flood_does_not_block -q --timeout=30`
Expected: PASS.

---

### Task 3: Generation-based multi-waiter diagnostics

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/client.py`
- Test: `packages/agentbox-harness/tests/test_lsp_client.py`

**Interfaces:**
- Produces: `sync_document(path, language, *, save=False) -> int`
  (returns the publish generation snapshot).
- Produces: `diagnostics(path, since_gen=None) -> list[dict]`.
- Produces: `wait_for_diagnostics(path, since_gen, *, first, settle, max_wait,
  quiescence=False) -> list[dict]`.

- [ ] **Step 1: Write failing tests**

```python
async def test_concurrent_waits_both_complete(tmp_path):
    server = LspServer(CLEAN_COMMAND, tmp_path, diagnostics_timeout=2.0)
    await server.start()
    try:
        path = tmp_path / "a.py"
        path.write_text("x = 1\n")
        gen = await server.sync_document(str(path), "python")
        results = await asyncio.gather(
            server.wait_for_diagnostics(str(path), gen, first=1.0, settle=0.1, max_wait=2.0),
            server.wait_for_diagnostics(str(path), gen, first=1.0, settle=0.1, max_wait=2.0),
        )
        assert results == [[], []]
    finally:
        await server.stop()


async def test_pre_change_publish_does_not_satisfy_wait(tmp_path):
    # fake server publishes an error on didOpen, then nothing on didChange
    ...
    gen = await server.sync_document(str(path), "python")
    result = await server.wait_for_diagnostics(
        str(path), gen, first=0.2, settle=0.1, max_wait=0.5
    )
    assert result == []
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_client.py -q --timeout=30`
Expected: FAIL (single event clobber; stale publish accepted).

- [ ] **Step 3: Implement**

Replace `_diagnostic_events` with:

```python
self._waiters: dict[pathlib.Path, set[asyncio.Event]] = {}
self._publish_gen: dict[pathlib.Path, int] = {}
```

On publish:

```python
self._diagnostics[key] = published
self._publish_gen[key] = self._publish_gen.get(key, 0) + 1
for event in list(self._waiters.get(key, ())):
    event.set()
```

Implement `wait_for_diagnostics` with an event and 50 ms tick as described in
the design. Remove the old `_settle_wait`/`_quiescence_wait` or fold their logic
into the new function. For quiescence, compute `busy_at_start =
tracker.busy_seq`; done when `tracker.quiescent is True` and
(`gen > since_gen` or `tracker.busy_seq > busy_at_start`).

`diagnostics(path, since_gen=None)`:

- Pull path unchanged, but handle `kind == "unchanged"` by returning cached.
- Push path calls `wait_for_diagnostics`.
- If `since_gen is None`, use `self._publish_gen.get(target, 0)`.

- [ ] **Step 4: Run the LSP client tests**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_client.py -q --timeout=60`
Expected: PASS.

---

### Task 4: Document LRU, sync lock, and didClose

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/client.py`
- Modify: `packages/agentbox-harness/tests/fake_lsp_server.py`
- Test: `packages/agentbox-harness/tests/test_lsp_client.py`

**Interfaces:**
- Produces: `LspServer.documents` (open count, existing).
- Produces: `LspServer.close_document(path)`.

- [ ] **Step 1: Write a failing LRU test**

Add `--track-close <file>` to the fake server: append each `didClose` URI.

```python
async def test_lru_closes_oldest_document(tmp_path):
    close_log = tmp_path / "closed.txt"
    command = [*PUSH_COMMAND, "--track-close", str(close_log)]
    server = LspServer(command, tmp_path, doc_limit=2)
    await server.start()
    try:
        for name in ("a.py", "b.py", "c.py"):
            path = tmp_path / name
            path.write_text("x = 1\n")
            await server.sync_document(str(path), "python")
        assert server.documents == 2
        assert "a.py" in close_log.read_text()
    finally:
        await server.stop()
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_client.py::test_lru_closes_oldest_document -q --timeout=30`
Expected: FAIL.

- [ ] **Step 3: Implement**

Add `_open_order: OrderedDict[pathlib.Path, None]` and `_sync_lock`. In
`sync_document`, wrap the mutation in `async with self._sync_lock`, touch the
document, and call `_enforce_doc_limit()`.

```python
async def _enforce_doc_limit(self):
    while len(self._open_order) > self.doc_limit:
        target, _ = self._open_order.popitem(last=False)
        await self._notify("textDocument/didClose", {"textDocument": {"uri": target.as_uri()}})
        self._versions.pop(target, None)
        self._diagnostics.pop(target, None)
        self._publish_gen.pop(target, None)
        self._waiters.pop(target, None)
```

Add `close_document(path)` that pops the path, sends `didClose`, and drops state.

- [ ] **Step 4: Run the client tests**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_client.py -q --timeout=60`
Expected: PASS.

---

### Task 5: Manager nearest-root, exponential retry, restart

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/manager.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/client.py` (stack name)
- Test: `packages/agentbox-harness/tests/test_lsp_manager.py`

**Interfaces:**
- Produces: `LspManager.server_for_path(project_root, path) -> tuple[LspStack, pathlib.Path, LspServer] | None`.
- Produces: `LspManager.resolve_root(stack, path, project_root) -> pathlib.Path`.
- Produces: `LspManager.warm(project_root) -> None`.
- Produces: `LspManager.health() -> list[dict]`.

- [ ] **Step 1: Write failing tests**

```python
async def test_server_uses_nearest_root(tmp_path):
    nested = tmp_path / "apps" / "web"
    nested.mkdir(parents=True)
    (nested / "package.json").write_text("{}")
    manager = LspManager()
    manager.stacks = [replace(TS_STACK, command=FAKE_COMMAND)]
    result = await manager.server_for_path(str(tmp_path), str(nested / "a.ts"))
    assert result is not None
    _stack, root, _server = result
    assert root == nested
    await manager.shutdown()


async def test_failures_back_off_and_reset(tmp_path):
    manager = LspManager()
    manager.failure_backoff = 4.0
    manager.stacks = [replace(TS_STACK, command=("missing-binary",))]
    assert await manager.get_or_start(tmp_path, manager.stacks[0]) is None
    assert manager._failure_attempts[((tmp_path, "typescript"))] == 1
    # a successful start clears the counter
    manager.stacks = [replace(TS_STACK, command=FAKE_COMMAND)]
    assert await manager.get_or_start(tmp_path, manager.stacks[0]) is not None
    assert (tmp_path, "typescript") not in manager._failure_attempts
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_manager.py -q --timeout=60`
Expected: FAIL.

- [ ] **Step 3: Implement**

Replace `_failed` timing with `_failure_attempts` and `_failed_at`:

```python
def _retry_delay(self, key) -> float:
    attempts = self._failure_attempts.get(key, 0)
    return min(self.failure_backoff, float(2 ** max(0, attempts - 1)))
```

`get_or_start` uses `time.monotonic() - self._failed_at.get(key, 0) < delay`.

Add `resolve_root`, `server_for_path`, `warm`, and `health`. Key servers by
`(str(root), stack.name)`. Pass `stderr_lines`, `doc_limit`,
`first_change_timeout`, `settle_window`, and `max_wait` into `LspServer`.

When a stored server is dead: `await server.stop()`, remove it, then create a new
one.

- [ ] **Step 4: Run manager tests**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_manager.py -q --timeout=60`
Expected: PASS.

---

### Task 6: Hook uses nearest root; settings; real tests

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/hooks.py`
- Modify: `packages/agentbox-api/src/agentbox_api/config.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/manager.py` (configure)
- Test: `packages/agentbox-harness/tests/test_lsp_hook.py`
- Test: `packages/agentbox-harness/tests/test_lsp_real.py`

**Interfaces:**
- Consumes: `LspManager.server_for_path`, `sync_document(..., save=...)`,
  `diagnostics(path, since_gen=...)`.

- [ ] **Step 1: Update the hook test for a nested root**

```python
async def test_hook_uses_nearest_root(tmp_path):
    nested = tmp_path / "apps" / "web"
    nested.mkdir(parents=True)
    (nested / "package.json").write_text("{}")
    manager = LspManager()
    manager.stacks = [replace(TS_STACK, command=FAKE_COMMAND)]
    hook = make_lsp_hook(manager, "s1", str(tmp_path))
    path = nested / "a.ts"
    path.write_text("const x: number = 1\n")
    ctx = ToolHookContext(tool_name="write_file", args={"path": str(path)}, root=tmp_path, result="ok")
    await hook(ctx)
    active = manager.active_for_session("s1")
    assert active[0]["root"] == str(nested)
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_hook.py -q --timeout=60`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `hooks.py`:

```python
resolved = await manager.server_for_path(project_root, path)
if resolved is None:
    return None
stack, root, server = resolved
language = language_for(stack, path)
generation = await server.sync_document(path, language, save=stack.save)
diagnostics = await server.diagnostics(path, since_gen=generation)
manager.record_active(session_id, str(root), stack, server)
```

Add settings to `config.py` and read them in `LspManager.configure` with
`getattr(settings, "lsp_max_open_documents", 50)` etc.

Update `test_lsp_real.py` to warm up before timing and to use the new hook
signature. Keep availability skips.

- [ ] **Step 4: Run harness tests**

Run: `uv run pytest packages/agentbox-harness -q --timeout=120`
Expected: PASS (real-server tests may skip).

---

### Task 7: Full verification

- [ ] **Step 1: Run package checks**

```powershell
uv run ruff check --fix packages
uv run ty check packages
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-api -q
```

Expected: no Ruff errors, no ty errors, all tests pass or skip.

- [ ] **Step 2: Record timings**

Run the focused real test with `-s` and capture cold/warm timings. Add the
numbers to the PR/commit notes when the user asks to commit.
