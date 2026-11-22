# Non-Blocking LSP Diagnostics — Design

Date: 2026-11-22
Status: Approved (design), spec awaiting review.
Depends on: `2026-11-22-lsp-foundations-design.md` (must land first).

## Goal

Remove diagnostics from the write tool's critical path while preserving the
automatic feedback loop. Writes return immediately; a background per-server
worker analyzes dirty files; the agent sees a compact, deduplicated diagnostic
reminder at the start of its next run and can pull full details with a new
`lsp_diagnostics` tool. The About endpoint exposes live snapshots and health.

## Why this shape

Comparison with opencode, Crush, Claude Code, and editor-integrated agents
(see `docs/research/2026-11-22-lsp-diagnostics-study.md`) shows three viable
patterns:

1. **Blocking with a short adaptive window** (opencode 3 s; Crush 1 s/300 ms/5 s).
2. **On-demand tool + editor-owned diagnostics** (Claude Code, VS Code agents,
   Pi extension).
3. **No LSP; run project checks** (Aider, Codex/Gemini CLIs, opencode docs).

Agentbox needs automatic feedback (the existing product promise), so pure
on-demand is insufficient. Blocking every write is the current efficiency
problem. The chosen design is **asynchronous automatic delivery plus on-demand
detail**, with the existing blocking path removable without losing feedback.

## Architecture

### Snapshot model (`lsp/diagnostics.py`)

```python
@dataclass(frozen=True)
class DiagnosticsSnapshot:
    path: str
    stack: str
    root: str
    generation: int
    state: str                  # pending | ready | error | timeout
    diagnostics: tuple[dict, ...]
    updated_at: float
    error: str | None = None

    @property
    def errors(self) -> list[dict]: ...
    @property
    def warnings(self) -> list[dict]: ...
```

Snapshots are stored per absolute path. They are immutable; replacements keep
the newest generation.

### `DiagnosticsService` (`lsp/diagnostics.py`)

One module-level service, configured alongside `LspManager`.

Responsibilities:

- Accept write notifications without blocking on server startup or analysis.
- Coalesce rapid writes to the same path into one analysis job.
- Resolve the stack/root/server through `LspManager.server_for_path`.
- Sync the document, wait adaptively, and store a snapshot.
- Provide cheap reads for the reminder and API.
- Provide a bounded refresh for the on-demand tool.

Internal state:

```python
self._queued: dict[Path, Job]                 # coalescing queue
self._wake: asyncio.Event
self._worker: asyncio.Task | None
self._snapshots: dict[Path, DiagnosticsSnapshot]
self._jobs_in_flight: dict[Path, asyncio.Future[DiagnosticsSnapshot]]
self._touched_by_session: dict[str, set[Path]]
self._delivered_gen: dict[tuple[str, Path], int]
self._lock: asyncio.Lock
```

API:

```python
def note_write(self, session_id: str, project_root: str, path: str) -> None
async def refresh(self, session_id, project_root, path, *, timeout=None) -> DiagnosticsSnapshot
def snapshot(self, path) -> DiagnosticsSnapshot | None
def snapshots_for_session(self, session_id) -> list[DiagnosticsSnapshot]
def project_snapshot(self, project_root) -> list[DiagnosticsSnapshot]  # cached only
async def reminder(self, session_id) -> str | None
async def shutdown(self) -> None
```

`note_write` is synchronous: it records the path for the session, stores/replace
a `Job(session_id, project_root, path)`, sets `_wake`, and ensures the worker
task exists. If a job for the path is already queued, the newer job replaces it.
If a job is in flight, the new job is queued and will run after the current one
(coalescing still applies while the worker is busy).

Worker loop:

1. `await self._wake.wait(); self._wake.clear()`.
2. Pop all queued jobs (`list(self._queued.values())`; clear the dict).
3. For each job, create/reuse a future in `_jobs_in_flight`, then process.
4. `finally`: resolve the future with the snapshot (or an error snapshot) and
   remove it from `_jobs_in_flight`.

`_process(job)`:

- Resolve `(stack, root, server) = await manager.server_for_path(...)`.
  If `None`: snapshot `state="error"` with a short `error="LSP server
  unavailable"` and return.
- `generation = await server.sync_document(path, language, save=stack.save)`.
- If pull is available: `diagnostics = await server.diagnostics(path)`.
- Else: `diagnostics = await server.wait_for_diagnostics(
  path, generation, first=stack.first_change_timeout,
  settle=stack.settle_window,
  max_wait=service.max_wait)`. The service default `max_wait` is
  `settings.lsp_diagnostics_timeout`.
- Store `DiagnosticsSnapshot(state="ready", generation=..., diagnostics=tuple(...),
  updated_at=time.time())`.
- On timeout: snapshot `state="timeout"` with the cached diagnostics.
- On exception: snapshot `state="error"` with `error=str(exc)` and log.

`refresh`:

- If a snapshot exists and is newer than `timeout`? No: refresh always requests a
  new analysis, because the file may have changed on disk without a write hook
  (e.g. a shell command).
- Queue a job and await its future with `asyncio.wait_for(timeout)`.
- On timeout, return the latest snapshot with `state="timeout"` (or a synthetic
  error snapshot if none).

`reminder(session_id)`:

- Select snapshots whose path is in `_touched_by_session[session_id]`.
- Keep only snapshots with at least one severity-1 diagnostic.
- Skip snapshots whose generation is `<= _delivered_gen[(session_id, path)]`.
- Format at most 5 files and at most 3 errors per file:

```text
<lsp_diagnostics>
2 files have errors after your edits:
- C:\repo\src\main.rs:4:8 cannot find value `x` (rust-analyzer)
- C:\repo\src\lib.rs:12:5 expected `;` (rust-analyzer)
... 3 more files. Call lsp_diagnostics for full details.
</lsp_diagnostics>
```

- Mark each included path's generation as delivered and return the text, or
  `None` when there is nothing new.
- Only errors (severity 1) are delivered automatically. Warnings/info are
  available through the tool and UI.

### Hook (`lsp/hooks.py`)

Replace `make_lsp_hook` with `make_lsp_notify_hook(service, session_id, project_root)`:

- Only for `WRITE_TOOLS`.
- Resolve `path` from `ctx.args`; return `None` if missing.
- `service.note_write(session_id, project_root, path)`.
- Return `None` (no text appended).
- Exceptions are logged and swallowed by the registry as today.

The hook must not call `await` on any LSP operation. Its cost is a dict insert
and an event set.

### On-demand tool (`lsp/diagnostics.py`)

`make_lsp_diagnostics_tool(service, session_id, project_root) -> Callable`:

```python
async def lsp_diagnostics(
    path: str | None = None,
    severity: str = "error",   # error | warning | all
    limit: int = 20,
) -> str:
```

- `path` is resolved within `project_root`; paths outside are rejected with a
  clear message.
- With a path: `snapshot = await service.refresh(session_id, project_root, path,
  timeout=service.max_wait)`, then format.
- Without a path: return cached snapshots for the session (no refresh of the
  whole project), grouped by file, errors first, capped at `limit` lines.
- Severity filter: `error` = severity 1, `warning` = 2, `all` = 1/2/3/4.
- Output format:

```text
LSP diagnostics for C:\repo\src\main.rs (rust, 2 errors, 1 warning)
  4:8 error cannot find value `x` (rust-analyzer)
 12:5 warning unused variable `y` (rust-analyzer)
```

- If there are none: `No LSP diagnostics for <path>.`
- If the server is unavailable: `LSP unavailable: <reason>`.

Tool registration:

- `prepare_agent` registers it in `extra_tools` when `lsp_enabled` and
  `session_id` are present.
- Add `NativeToolBinding(name="lsp_diagnostics")` to the spec, following the
  `PLAN_TOOL_NAMES` pattern.
- Register with no required mode flags so it is available in read-only modes
  (reading diagnostics is safe).

### Reminder delivery (`Harness`)

Add a `SessionReminder` protocol:

```python
class SessionReminder(Protocol):
    async def reminder(self, session: Session) -> str | None: ...
```

`Harness.__init__` accepts `reminders: list[SessionReminder] | None = None`.

In `Harness.run`, after appending the user turn and before starting the run:

1. For each reminder provider, `text = await provider.reminder(session)`.
2. Join non-empty texts with `"\n\n"`.
3. If `prompt_override is None`: `effective_prompt = user_message + "\n\n" +
   reminder_text`.
4. Else: `effective_override = [*prompt_override, reminder_text]`.
5. Pass `effective_prompt` / `effective_override` to `RunManager.start`.

The persisted `Turn` content remains the original user message. The reminder is
transient and regenerated on retry/fork.

`DiagnosticsReminder(service)` implements `SessionReminder` by delegating to
`service.reminder(session.session_id)`.

Wiring: all `Harness(...)` construction sites pass
`reminders=[DiagnosticsReminder(get_diagnostics_service())]` when LSP is enabled.
To avoid four copies, add a small helper in `agentbox_api/runtime.py`:

```python
def lsp_reminders() -> list[SessionReminder]:
    if not get_lsp_manager().enabled:
        return []
    return [DiagnosticsReminder(get_diagnostics_service())]
```

### Startup and shutdown

- `app.py` lifespan: `get_diagnostics_service().shutdown()` before
  `get_lsp_manager().shutdown()`.
- `configure_lsp(settings)` also configures the diagnostics service (max wait,
  project/session caps).
- On the first `prepare_agent` for a project, schedule `manager.warm(project_root)`
  as a background task so `uvx`/`npx` provisioning and rust-analyzer cold start
  happen before the first write. Only if `lsp_warm_on_start` is true (default
  false; opt-in warm-up avoids starting servers for every test or read-only
  session). Failures are logged and ignored.

### API and UI

Extend `GET /sessions/{sid}/lsp`:

```json
{
  "detected": ["python", "typescript"],
  "active": [
    {
      "stack": "rust",
      "command": "rust-analyzer",
      "root": "C:\\repo",
      "status": "running",
      "state": "ready",
      "documents": 3,
      "last_error": null
    }
  ],
  "snapshots": [
    {
      "path": "C:\\repo\\src\\main.rs",
      "stack": "rust",
      "state": "ready",
      "errors": 1,
      "warnings": 0,
      "updated_at": 1764000000.0
    }
  ]
}
```

- `snapshots` is derived from `service.snapshots_for_session(sid)`. Do not expose
  full diagnostic lists here; the tool returns details.
- Regenerate `apps/web/openapi.json` and `apps/web/src/api/schema.d.ts` with the
  documented scripts.
- `SessionPage` About modal:
  - show server `state` and `last_error` when present;
  - add a "Problems" section listing snapshot paths and error/warning counts;
  - keep the existing detected/active lists and error handling.

If codegen cannot run in the environment, do not hand-edit the generated schema;
ship the backend endpoint change and leave the UI task as a follow-up.

## Settings

Add to `config.py`:

```python
lsp_mode: str = "auto"              # auto | on_demand | off
lsp_max_open_documents: int = 50
lsp_first_change_timeout: float = 1.0
lsp_settle_window: float = 0.3
lsp_warm_on_start: bool = False
lsp_session_snapshot_limit: int = 100
```

Semantics:

- `auto`: background analysis + reminder + tool (default).
- `on_demand`: no background job on write; only the `lsp_diagnostics` tool and
  the About snapshots (which update when the tool runs).
- `off`: no servers, no hook, no tool. `lsp_enabled=False` remains an alias for
  `off`.

`lsp_enabled` stays for backward compatibility; `lsp_mode` takes precedence when
present. Document both.

## Delivery and token rules

- Automatic reminders contain only severity-1 errors, max 5 files, max 3 errors
  per file, and a pointer to the tool.
- Warnings are never delivered automatically.
- A path's reminder is suppressed until its diagnostic generation advances.
- Snapshot lists are per session to avoid leaking project-wide noise into a
  focused session.
- The on-demand tool is the only path that returns full messages and ranges.

## Testing

### Service unit tests (`test_lsp_diagnostics.py`)

- `note_write` returns immediately even when the server takes seconds to start
  (use a fake server with `--slow-init`).
- Rapid writes to one path coalesce into one analysis job.
- Writes to two paths are processed independently.
- A reminder contains only errors, is deduplicated by generation, and points to
  the tool.
- `refresh` times out with `state="timeout"` and returns the cached list.
- Server unavailable produces `state="error"` without raising.
- `shutdown` cancels the worker and resolves pending futures.

### Tool tests

- `lsp_diagnostics(path=...)` refreshes and formats errors/warnings.
- `lsp_diagnostics()` returns session snapshots only.
- Invalid severity is rejected.
- Paths outside the project root are rejected.
- Clean file returns "No LSP diagnostics".
- Tool registration adds it to the agent's tool list and bindings.

### Harness tests

- A reminder provider appends text to the prompt passed to
  `RunManager.start` (use a fake run manager or inspect the agent prompt).
- Persisted user turns do not contain the reminder.
- Multiple providers join with blank lines.
- `prompt_override` receives the reminder as an extra text part.

### Integration tests

- Write a file with the fake server in `--server-status`/push mode: the tool
  result returns immediately, then `lsp_diagnostics` (or the next run's
  reminder) contains the error.
- `GET /sessions/{sid}/lsp` returns snapshots and health fields.
- `lsp_mode="off"` disables hook, tool, and reminder.

### Real server test

- Warm Rust project: a write returns in < 100 ms (no LSP wait); a reminder or
  explicit tool call within a few seconds reports the error.

## Out of scope

- Project check commands (`cargo check`, `tsc --noEmit`, `ty check`) as a
  first-class feature. Document them in `AGENTS.md`/skills as the recommended
  fallback.
- Hover/references/code actions/rename.
- Incremental sync.
- Streaming diagnostics into the UI via SSE; the About modal polls the endpoint.
- Persisting snapshots across process restarts.
- Multi-root workspace folders beyond nearest-root selection.
