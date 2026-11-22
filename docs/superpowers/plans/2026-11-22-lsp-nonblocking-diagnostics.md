# Non-Blocking LSP Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make writes return immediately, analyze edited files in the background, deliver compact diagnostics to the next agent run, and expose an on-demand `lsp_diagnostics` tool plus session snapshots.

**Architecture:** A `DiagnosticsService` coalesces dirty paths into a background worker, stores immutable snapshots, and provides reminder/tool formatting. The write hook only enqueues. `Harness` injects reminders into the transient prompt. The API exposes snapshot counts and health.

**Tech Stack:** Python 3.11+, asyncio, pytest/pytest-asyncio, FastAPI, React/Vite.

## Global Constraints

- Do **not** commit unless the user explicitly asks.
- Preserve `lsp_enabled` behaviour; add `lsp_mode` with `auto` as the default.
- Automatic reminders: severity-1 only, max 5 files, max 3 errors/file.
- The write hook must never await LSP work.
- One package per pytest invocation.
- Checks: `uv run ruff check --fix packages`, `uv run ty check packages`.

---

### Task 1: Snapshot model and coalescing service

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/lsp/diagnostics.py`
- Test: `packages/agentbox-harness/tests/test_lsp_diagnostics.py`

**Interfaces:**
- Produces: `DiagnosticsSnapshot` dataclass with `path, stack, root, generation,
  state, diagnostics, updated_at, error`, and `errors`/`warnings` properties.
- Produces: `DiagnosticsService(manager, *, max_wait=5.0, session_limit=100)`
  with `note_write`, `refresh`, `snapshot`, `snapshots_for_session`,
  `project_snapshot`, `reminder`, `shutdown`.
- Produces: module singleton `get_diagnostics_service()` and
  `configure_diagnostics(settings)`.

- [ ] **Step 1: Write failing service tests**

```python
import asyncio
import pathlib

from agentbox_harness.lsp.diagnostics import DiagnosticsService
from agentbox_harness.lsp.manager import LspManager


async def test_note_write_returns_immediately(tmp_path, fake_stack):
    manager = LspManager()
    manager.stacks = [fake_stack("--slow-init", "2")]
    service = DiagnosticsService(manager, max_wait=3.0)
    path = tmp_path / "a.py"
    path.write_text("x = 1\n")
    loop = asyncio.get_running_loop()
    start = loop.time()
    service.note_write("s1", str(tmp_path), str(path))
    assert loop.time() - start < 0.05
    snap = await service.refresh("s1", str(tmp_path), str(path), timeout=3.0)
    assert snap.state == "ready"
    await service.shutdown()
    await manager.shutdown()


async def test_rapid_writes_coalesce(tmp_path, fake_stack):
    manager = LspManager()
    manager.stacks = [fake_stack()]
    service = DiagnosticsService(manager)
    path = tmp_path / "a.py"
    path.write_text("x = 1\n")
    for _ in range(10):
        service.note_write("s1", str(tmp_path), str(path))
    await asyncio.sleep(0.1)
    assert service._analysis_count == 1
    await service.shutdown()
    await manager.shutdown()
```

Add a `fake_stack` fixture in the test module that builds an `LspStack` pointing
at `tests/fake_lsp_server.py` with the extra args.

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_diagnostics.py -q --timeout=60`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement the service**

Create `diagnostics.py`:

```python
@dataclass(frozen=True)
class DiagnosticsSnapshot:
    path: str
    stack: str
    root: str
    generation: int
    state: str
    diagnostics: tuple[dict, ...] = ()
    updated_at: float = 0.0
    error: str | None = None

    @property
    def errors(self):
        return [d for d in self.diagnostics if d.get("severity", 1) == 1]

    @property
    def warnings(self):
        return [d for d in self.diagnostics if d.get("severity", 1) == 2]


class DiagnosticsService:
    def __init__(self, manager, *, max_wait=5.0, session_limit=100):
        self.manager = manager
        self.max_wait = max_wait
        self.session_limit = session_limit
        self._queued = {}
        self._wake = asyncio.Event()
        self._worker = None
        self._snapshots = {}
        self._inflight = {}
        self._touched = {}
        self._delivered = {}
        self._analysis_count = 0
        self._lock = asyncio.Lock()

    def note_write(self, session_id, project_root, path):
        target = pathlib.Path(path).resolve()
        self._touched.setdefault(session_id, set()).add(target)
        self._queued[target] = (session_id, project_root, str(target))
        self._wake.set()
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run())

    async def _run(self):
        while True:
            await self._wake.wait()
            self._wake.clear()
            jobs = list(self._queued.values())
            self._queued.clear()
            for job in jobs:
                await self._process(job)

    async def _process(self, job):
        session_id, project_root, path = job
        target = pathlib.Path(path)
        self._analysis_count += 1
        try:
            resolved = await self.manager.server_for_path(project_root, path)
            if resolved is None:
                snap = DiagnosticsSnapshot(path, "", project_root, 0, "error",
                                           error="LSP server unavailable")
            else:
                stack, root, server = resolved
                language = language_for(stack, path)
                generation = await server.sync_document(path, language, save=stack.save)
                diagnostics = await server.diagnostics(path, since_gen=generation)
                snap = DiagnosticsSnapshot(path, stack.name, str(root), generation,
                                           "ready", tuple(diagnostics), time.time())
        except TimeoutError:
            snap = self._snapshot_or(path, "timeout", "LSP analysis timed out")
        except Exception as exc:
            snap = self._snapshot_or(path, "error", str(exc))
        self._snapshots[target] = snap
        fut = self._inflight.pop(target, None)
        if fut and not fut.done():
            fut.set_result(snap)
```

`refresh` creates a future, calls `note_write`, and awaits with
`asyncio.wait_for`. `_snapshot_or` returns the existing snapshot with the new
state or a synthetic one. `shutdown` cancels the worker and resolves pending
futures with an error snapshot.

- [ ] **Step 4: Run the service tests**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_diagnostics.py -q --timeout=60`
Expected: PASS.

---

### Task 2: Reminder formatting and deduplication

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/diagnostics.py`
- Test: `packages/agentbox-harness/tests/test_lsp_diagnostics.py`

**Interfaces:**
- Produces: `DiagnosticsService.reminder(session_id) -> str | None`.
- Produces: `format_snapshot(snapshot, severity="error", limit=20) -> str`.
- Produces: `format_reminder(snapshots, delivered) -> str | None` (pure helper).

- [ ] **Step 1: Write failing tests**

```python
def test_reminder_only_errors_and_dedupes():
    snaps = [
        DiagnosticsSnapshot("a.py", "python", "/r", 2, "ready",
                            ({"severity": 1, "message": "boom",
                              "range": {"start": {"line": 3, "character": 7}}},)),
    ]
    service = DiagnosticsService(manager=object())
    service._snapshots[pathlib.Path("a.py")] = snaps[0]
    service._touched["s1"] = {pathlib.Path("a.py")}
    first = asyncio.run(service.reminder("s1"))
    assert "boom" in first and "<lsp_diagnostics>" in first
    assert asyncio.run(service.reminder("s1")) is None
```

Add a warning-only snapshot and assert it is ignored.

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_diagnostics.py -q --timeout=60`
Expected: FAIL.

- [ ] **Step 3: Implement**

Format errors as `path:line:col message (source)`. Use at most 5 files and 3
errors each. Mark `_delivered[(session_id, path)] = snapshot.generation` for the
files included. Return `None` when nothing new or no errors.

`format_snapshot` supports `severity` in `error|warning|all` and caps lines.
Return `No LSP diagnostics for <path>.` when empty.

- [ ] **Step 4: Run the service tests**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_diagnostics.py -q --timeout=60`
Expected: PASS.

---

### Task 3: Notify-only hook and `lsp_diagnostics` tool

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/hooks.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/lsp/diagnostics.py`
- Test: `packages/agentbox-harness/tests/test_lsp_hook.py`
- Test: `packages/agentbox-harness/tests/test_lsp_diagnostics.py`

**Interfaces:**
- Produces: `make_lsp_notify_hook(service, session_id, project_root)`.
- Produces: `make_lsp_diagnostics_tool(service, session_id, project_root)`.
- Removes: `make_lsp_hook` and its blocking behaviour.

- [ ] **Step 1: Write failing tests**

```python
async def test_notify_hook_does_not_wait(service, tmp_path):
    hook = make_lsp_notify_hook(service, "s1", str(tmp_path))
    ctx = ToolHookContext("write_file", {"path": str(tmp_path / "a.py")},
                          tmp_path, "ok")
    assert await hook(ctx) is None
    assert len(service._queued) == 1


async def test_tool_formats_diagnostics(service, tmp_path):
    tool = make_lsp_diagnostics_tool(service, "s1", str(tmp_path))
    path = tmp_path / "a.py"
    path.write_text("x: int = 'no'\n")
    text = await tool(path=str(path))
    assert "error" in text
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_hook.py -q --timeout=60`
Expected: FAIL.

- [ ] **Step 3: Implement**

`make_lsp_notify_hook` calls `service.note_write(...)` and returns `None`.
`make_lsp_diagnostics_tool`:

```python
async def lsp_diagnostics(path=None, severity="error", limit=20):
    if severity not in {"error", "warning", "all"}:
        return "severity must be error, warning, or all"
    if path:
        target = (pathlib.Path(project_root) / path).resolve()
        if pathlib.Path(project_root).resolve() not in target.parents:
            return "path is outside the project"
        snap = await service.refresh(session_id, project_root, str(target))
        return format_snapshot(snap, severity, limit)
    snaps = service.snapshots_for_session(session_id)
    return format_project(snaps, severity, limit)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest packages/agentbox-harness/tests/test_lsp_hook.py packages/agentbox-harness/tests/test_lsp_diagnostics.py -q --timeout=60`
Expected: PASS.

---

### Task 4: Harness reminder injection

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/harness.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/middleware.py`
- Test: `packages/agentbox-harness/tests/test_harness_reminders.py`

**Interfaces:**
- Produces: `SessionReminder` protocol in `middleware.py`.
- Produces: `Harness(..., reminders: list[SessionReminder] | None = None)`.
- Consumes: `DiagnosticsService.reminder`.

- [ ] **Step 1: Write failing tests**

Use a fake `RunManager` that captures `prompt`/`prompt_override`, and a fake
reminder:

```python
class FakeReminder:
    async def reminder(self, session):
        return "<lsp_diagnostics>boom</lsp_diagnostics>"


async def test_reminder_is_appended_to_prompt(harness, session, fake_run_manager):
    harness.run_manager = fake_run_manager
    harness.reminders = [FakeReminder()]
    await harness.run(session, "hello", EventBus())
    assert fake_run_manager.last_prompt.endswith("boom</lsp_diagnostics>")


async def test_reminder_not_persisted(harness, session, fake_run_manager):
    ...
    turns = await session.store.list_turns()
    assert "lsp_diagnostics" not in turns[-1].content
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-harness/tests/test_harness_reminders.py -q --timeout=60`
Expected: FAIL.

- [ ] **Step 3: Implement**

Add the protocol and constructor parameter. In `run`, after appending the user
turn:

```python
texts = []
for provider in self.reminders:
    text = await provider.reminder(session)
    if text:
        texts.append(text)
reminder = "\n\n".join(texts)
effective_prompt = user_message if not reminder else f"{user_message}\n\n{reminder}"
effective_override = prompt_override
if prompt_override is not None and reminder:
    effective_override = [*prompt_override, reminder]
```

Pass `effective_prompt`/`effective_override` to `run_manager.start`. Keep the
persisted `Turn` content as `user_message`.

- [ ] **Step 4: Run harness tests**

Run: `uv run pytest packages/agentbox-harness -q --timeout=120`
Expected: PASS.

---

### Task 5: API wiring, settings, warm-up, endpoint

**Files:**
- Create: `packages/agentbox-api/src/agentbox_api/lsp_runtime.py`
- Modify: `packages/agentbox-api/src/agentbox_api/config.py`
- Modify: `packages/agentbox-api/src/agentbox_api/skills.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`
- Modify: `packages/agentbox-api/src/agentbox_api/acp_server.py`
- Modify: `packages/agentbox-api/src/agentbox_api/a2a_executor.py`
- Modify: `packages/agentbox-api/src/agentbox_api/subagent_sessions.py`
- Modify: `packages/agentbox-api/src/agentbox_api/app.py`
- Test: `packages/agentbox-api/tests/test_session_lsp.py`
- Test: `packages/agentbox-api/tests/test_lsp_wiring.py`

**Interfaces:**
- Produces: `lsp_enabled()`/`lsp_reminders()` helpers in `lsp_runtime.py`.
- Produces: `make_lsp_notify_hook`, `make_lsp_diagnostics_tool` wiring.
- Produces: endpoint `snapshots` and `active[].state/last_error`.

- [ ] **Step 1: Write failing wiring tests**

```python
def test_agent_has_lsp_diagnostics_tool(prepare_agent):
    prepared = prepare_agent(...)
    names = {b.name for b in prepared.spec.tool_bindings}
    assert "lsp_diagnostics" in names


async def test_session_lsp_returns_snapshots(client, session):
    response = await client.get(f"/sessions/{session.id}/lsp")
    assert response.status_code == 200
    assert "snapshots" in response.json()
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-api/tests/test_lsp_wiring.py packages/agentbox-api/tests/test_session_lsp.py -q --timeout=60`
Expected: FAIL.

- [ ] **Step 3: Implement**

- `lsp_runtime.py`:

```python
def lsp_enabled(manager):
    return manager.enabled and manager.mode != "off"

def lsp_reminders(manager, service):
    return [DiagnosticsReminder(service)] if lsp_enabled(manager) and manager.mode == "auto" else []
```

- `skills.py`: register `lsp_diagnostics` in `extra_tools`; add
  `NativeToolBinding(name="lsp_diagnostics")` when enabled; use
  `make_lsp_notify_hook`; schedule `asyncio.create_task(manager.warm(project_root))`
  when `settings.lsp_warm_on_start` (opt-in, default false).
- Harness construction sites: pass `reminders=lsp_reminders(...)`.
- `app.py`: configure the diagnostics service and shut it down first.
- Endpoint: append

```python
"snapshots": [
    {"path": s.path, "stack": s.stack, "state": s.state,
     "errors": len(s.errors), "warnings": len(s.warnings),
     "updated_at": s.updated_at}
    for s in get_diagnostics_service().snapshots_for_session(sid)
]
```

and include `state`, `last_error` from `active_for_session`.

- [ ] **Step 4: Regenerate API artifacts**

```powershell
uv run python apps/web/scripts/gen-openapi.py
cd apps/web
bun run codegen
```

If codegen dependencies are unavailable, stop and report; do not hand-edit the
schema.

- [ ] **Step 5: Run API tests**

Run: `uv run pytest packages/agentbox-api -q --timeout=120`
Expected: PASS.

---

### Task 6: About UI problems section

**Files:**
- Modify: `apps/web/src/pages/SessionPage.tsx`
- Test: `apps/web/src/pages/SessionPage.ux4.test.tsx`
- Test: `apps/web/src/pages/SessionPage.avatar.test.tsx`

- [ ] **Step 1: Add a failing UI test**

```tsx
test("lists LSP problem snapshots in About", async () => {
  mockLsp({
    detected: [],
    active: [],
    snapshots: [{ path: "src/a.py", stack: "python", state: "ready",
                  errors: 2, warnings: 1, updated_at: 1 }],
  });
  // open About
  expect(await screen.findByText("src/a.py")).toBeInTheDocument();
  expect(screen.getByText(/2 errors/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run and verify failure**

Run: `cd apps/web && bun run test -- SessionPage`
Expected: FAIL.

- [ ] **Step 3: Implement**

Render a "Problems" section under active servers; show `state`/`last_error` and
snapshot rows. Keep the existing error/retry UI.

- [ ] **Step 4: Run frontend tests and build**

```powershell
cd apps/web
bun run test
bun run build
```

Expected: PASS.

---

### Task 7: End-to-end timing and cleanup

- [ ] **Step 1: Add an integration test**

Use the fake server: a `write_file` hook call returns in < 50 ms; then
`lsp_diagnostics` returns the error; the next `Harness.run` reminder contains the
error.

- [ ] **Step 2: Verify all packages**

```powershell
uv run ruff check --fix packages
uv run ty check packages
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-api -q
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-providers -q
```

Expected: clean checks; tests pass or skip.

- [ ] **Step 3: Measure**

Record write-hook latency p50/p95, time-to-first-reminder, and timeout counts in
the final report or commit message (only when the user asks to commit).
