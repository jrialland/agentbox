# LSP Foundations — Design

Date: 2026-11-22
Status: Approved (design), spec awaiting review.
Roadmap: LSP efficiency/reliability follow-up to D19.

## Goal

Fix the correctness, lifecycle, and latency defects in the current in-process LSP
runtime before changing the user-facing diagnostics flow. After this phase the
same blocking `write_file`/`append_file`/`edit_file` hook remains, but it resolves
the right server root, cannot deadlock on stderr, cannot return stale or
cross-file diagnostics, and recovers from crashes. Phase 2
(`2026-11-22-lsp-nonblocking-diagnostics-design.md`) builds on this runtime.

## Current defects

References are to the pre-change code.

1. **Undrained stderr pipe.** `client.py:67-73` spawns with
   `stderr=asyncio.subprocess.PIPE` and never reads it. rust-analyzer and
   `npx`/`uvx` write heavily to stderr; when the OS pipe buffer fills the child
   blocks and stops serving LSP messages.
2. **Project-root-only servers.** Detection scans the whole session root, and
   `initialize` always uses that root (`client.py:75-92`). Monorepos start
   tsserver/rust-analyzer at the wrong root.
3. **Unpruned detection.** `detect.py:15-25` runs `Path.glob("**/...")` and
   filters matches afterward, so `node_modules`, `.venv`, `target`, and `dist`
   are traversed.
4. **Single-slot waiters.** `_diagnostic_events` is a `dict[Path, Event]`
   (`client.py:52-53`). Concurrent writes to one path overwrite each other's
   event; one caller waits until timeout.
5. **No version gate.** Waits are not tied to the write generation, so a publish
   that happened before the `didChange` can satisfy a wait.
6. **No document lifecycle.** Documents are never closed; `_versions`,
   `_diagnostics`, and `_publish_counts` grow for the process lifetime.
7. **Flat failure blacklist.** Any init failure suppresses the stack for
   `lsp_failure_backoff_seconds` (default 60 s) with no retry/backoff/health.
8. **Dead servers are replaced, not stopped** (`manager.py:48-64`).
9. **Narrow server-request handling** (`client.py:143-167`): unknown or common
   requests receive method-not-found, which can stall some servers.
10. **No watched-file notifications** after edits that affect other files.

## Decisions

- **Nearest-root per file, not per project.** A stack gains `root_markers`
  (plain file names). The manager walks from the edited file's directory up to
  the session root and initializes the server at the nearest directory
  containing any marker. If none is found, the session root is used.
- **Per-file stack selection.** The hook no longer requires the session-wide
  detection result. It picks a configured stack by file extension, so a single
  `.rs`/`.py`/`.ts` file works even when no marker exists.
- **Detection stays for reporting and future warm-up**, not for correctness.
  Replace `glob` with a pruned `os.walk`, bounded by an entry cap, and cache per
  project root.
- **Generation-based push waits.** Every `publishDiagnostics` increments a
  per-path generation. A wait snapshots the generation after `didChange`/`didSave`
  and only accepts publishes newer than that snapshot.
- **Fan-out waiters.** A path maps to a set of `asyncio.Event`s. Publishes wake
  all of them; each waiter re-checks the generation.
- **Serialized document mutations.** A per-server `asyncio.Lock` covers
  `didOpen`/`didChange`/`didSave`/`didClose` version bookkeeping. Waits run
  outside the lock, so one slow file does not block edits to others.
- **Bounded documents and caches.** Maintain an LRU of open documents
  (`lsp_max_open_documents`, default 50). Evicting sends `didClose` and drops
  that path's versions, diagnostics, and generation.
- **Explicit state machine and restart.** Every server reports
  `starting|ready|error|stopped`, the last error, and a stderr tail. A dead
  server is stopped and replaced on the next request.
- **Exponential retry, not a flat blacklist.** Failures back off `1, 2, 4, 8, …`
  seconds up to `lsp_failure_backoff_seconds`. A successful start clears the
  failure count.
- **No new stacks or features.** Hover, references, code actions, and project
  checks are out of scope for this phase.
- **Keep the blocking hook in this phase.** It uses the new runtime unchanged in
  shape; Phase 2 replaces the delivery mechanism.

## Architecture

### `LspStack` (`lsp/stacks.py`)

```python
@dataclass(frozen=True)
class LspStack:
    name: str
    markers: tuple[str, ...]          # detection globs (About panel / warm-up)
    command: tuple[str, ...]
    languages: tuple[str, ...]
    extensions: tuple[str, ...]
    root_markers: tuple[str, ...] = () # plain filenames for nearest-root search
    pull: bool = True
    save: bool = False
    settle: float = 3.0               # legacy upper bound
    quiescence: str | None = None
    first_change_timeout: float = 1.0 # adaptive wait: exit if nothing changes
    settle_window: float = 0.3        # adaptive wait: stability window
    post_quiescence_grace: float = 0.5 # wait for late non-empty diagnostics
```

Defaults:

- Python `root_markers=("pyproject.toml", "setup.py", "setup.cfg",
  "requirements.txt", "Pipfile", "pyrightconfig.json")`
- TypeScript `root_markers=("package-lock.json", "bun.lockb", "bun.lock",
  "pnpm-lock.yaml", "yarn.lock", "tsconfig.json", "package.json")`
- Rust `root_markers=("Cargo.toml",)` and `quiescence="server_status"`,
  `pull=False`, `save=True`.
- `first_change_timeout=1.0`, `settle_window=0.3` for all stacks.
- Rust uses `post_quiescence_grace=0.5`; other stacks use the 0.5 default.

`language_for` and `LANGUAGE_BY_EXTENSION` are unchanged.

### Detection (`lsp/detect.py`)

`detect_stacks(project_root, stacks=None)`:

- Walk with `os.walk`, pruning `PRUNE_PARTS` and dot-directories in-place
  (`dirnames[:] = kept`).
- Stop after `MAX_WALK_ENTRIES` (100_000) and log a warning.
- Collect relative POSIX file paths, then match each stack's `markers` with a
  helper that supports both `name` and `**/name` / `**/*.ext` forms:
  - `fnmatch(rel, marker)`
  - `fnmatch(rel, marker.removeprefix("**/"))`
  - `fnmatch(basename, marker.removeprefix("**/"))`
- Return stacks in definition order, each at most once.
- Cache remains in `LspManager.detected`.

Add:

```python
def stack_for_path(stacks, path) -> LspStack | None
def nearest_root(stack, path, fallback) -> pathlib.Path
```

`nearest_root` walks `Path(path).resolve().parent` upward while the directory is
inside `fallback`, returning the first directory where any `root_markers` entry
exists as a file. If `path` is outside `fallback` or no marker matches, returns
`fallback`.

### Client (`lsp/client.py`)

Constructor accepts `stderr_lines=200`, `doc_limit=50`, `first_change_timeout`,
`settle_window`, and `max_wait`.

State:

```python
self._versions: dict[Path, int]
self._diagnostics: dict[Path, list]
self._publish_gen: dict[Path, int]
self._waiters: dict[Path, set[asyncio.Event]]
self._open_order: OrderedDict[Path, None]
self._sync_lock: asyncio.Lock
self._stderr: deque[str]
self._state: str
self._last_error: str | None
```

Startup:

- Spawn as today, then start both `_read_loop()` and `_stderr_loop()`.
- `_stderr_loop` reads lines, stores up to `stderr_lines`, and debug-logs a
  truncated line. It never raises out of the task.
- Initialize as today; on error set `_state="error"`, record `_last_error`, and
  re-raise.

Reader:

- Parse `Content-Length` framing; reject payloads above a hard cap (e.g.
  50 MiB) with a logged transport error.
- On `textDocument/publishDiagnostics`:
  - resolve the URI to a path;
  - `self._diagnostics[path] = diagnostics`;
  - `self._publish_gen[path] = self._publish_gen.get(path, 0) + 1`;
  - wake all waiters for that path.
- On `experimental/serverStatus`, delegate to the tracker; wake tracker waiters.
- On a response, resolve or reject its pending future.
- On a server request, answer:
  - `workspace/configuration` → per-item `{}`;
  - `workspace/workspaceFolders` → `[{"uri": root_uri, "name": root.name}]`;
  - `workspace/applyEdit` → `{"applied": true}`;
  - `window/showDocument` → `{"success": true}`;
  - `window/showMessageRequest` → `null`;
  - `client/registerCapability`, `window/workDoneProgress/create`,
    `window/showMessage`, `window/logMessage` → `null`;
  - everything else → JSON-RPC method-not-found.
- On transport error or EOF: set `dead=True`, `_state="stopped"/"error"`, wake
  all waiters, and fail pending futures.

Document sync:

```python
async def sync_document(self, path, language, *, save=False) -> int:
    target = Path(path).resolve()
    async with self._sync_lock:
        text = target.read_text(encoding="utf-8")
        version = self._versions.get(target, 0) + 1
        if target not in self._versions:
            await self._notify("textDocument/didOpen", {... version ...})
        else:
            await self._notify("textDocument/didChange", {... version ...})
        self._versions[target] = version
        self._touch_document(target)
        await self._enforce_doc_limit()
        if save:
            await self._notify("textDocument/didSave", {...})
        return self._publish_gen.get(target, 0)
```

`_touch_document` moves the path to the end of `_open_order`.
`_enforce_doc_limit` pops the oldest path while over the limit, sends
`didClose`, and drops `_versions`, `_diagnostics`, `_publish_gen`, and waiters for
that path.

`save_document(path)` remains for callers that need a separate save, and uses
the sync lock.

Waiting:

```python
async def wait_for_diagnostics(
    self, path, since_gen, *, first, settle, max_wait, quiescence=False
) -> list[dict]:
```

- If the server is dead, return the cached list.
- If `_publish_gen[path] > since_gen`, skip the first-change wait.
- Otherwise wait up to `first` for a newer generation; if none arrives, return
  the cached list immediately.
- Once a newer generation is seen, poll (event-driven, 50 ms tick) until the
  generation has been stable for `settle`, or `max_wait` expires.
- When `quiescence=True` and the tracker has seen status, the completion
  condition is:
  `tracker.quiescent is True and (generation advanced or busy_seq advanced)`.
  If `tracker.seq == 0`, wait up to `first_change_timeout` for a status
  notification, then fall back to the generation-only wait.
- If quiescence is reached with only an empty publish, wait up to
  `post_quiescence_grace` for a non-empty publish (late native/flycheck
  diagnostics), then return the empty list. This keeps clean Rust edits fast
  without discarding diagnostics that arrive just after quiescence.
- If the server is already quiescent and neither a publish nor a busy toggle
  occurs within `max(first_change_timeout, post_quiescence_grace)`, return the
  cached result instead of waiting for `max_wait`.
- Always remove the waiter event in `finally`.

Pull path:

- If `pull` and the server advertised `diagnosticProvider`, send
  `textDocument/diagnostic` with `max_wait`.
- If the response `kind == "unchanged"`, return the cached list.
- Otherwise store and return `result.items`.
- Timeout returns the cached list (normally `[]`), never raises to the hook.

Health:

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

`stop()` cancels the reader and stderr tasks, sends `shutdown`/`exit`, and
terminates after a grace period.

### Manager (`lsp/manager.py`)

- `configure(settings)` also reads `lsp_max_open_documents`,
  `lsp_first_change_timeout`, `lsp_settle_window`.
- `detected(project_root)` stays cached.
- `resolve_root(stack, path, project_root)` delegates to `nearest_root`.
- `server_for_path(project_root, path) -> (stack, root, server) | None`:
  - iterate `self.stacks or DEFAULT_LSP_SERVERS` in order and pick the first
    stack for which `language_for(stack, path)` is not `None`;
  - resolve the nearest root;
  - `await get_or_start(root, stack)`.
- `get_or_start(root, stack)`:
  - key `(str(root), stack.name)`;
  - if a failure is recorded and the exponential delay has not elapsed, return
    `None`;
  - if a live server exists, return it;
  - if a dead server exists, `await stop()` and remove it;
  - create `LspServer` with the configured limits, `await start()`, clear the
    failure count, and store it;
  - on exception, increment the attempt count, record `time.monotonic()`, log a
    warning with the error, and return `None`.
- `warm(project_root)`: for each detected stack, start a server at the session
  root in the background (used by Phase 2; safe to call in Phase 1).
- `active_for_session` entries gain `state`, `last_error`, and `stderr_tail`
  from `server.health()`.
- `shutdown()` stops all servers and clears state.

### Hook (`lsp/hooks.py`)

No semantic change yet:

- `WRITE_TOOLS` unchanged.
- Use `manager.server_for_path(project_root, path)` instead of
  `manager.detected` + `get_or_start`.
- `generation = await server.sync_document(path, language, save=stack.save)`
  (remove the separate `save_document` call).
- `diagnostics = await server.diagnostics(path, since_gen=generation)`.
- Format and return as today.
- Record the active stack for the session.

## Settings

Add to `packages/agentbox-api/src/agentbox_api/config.py`:

```python
lsp_max_open_documents: int = 50
lsp_first_change_timeout: float = 1.0
lsp_settle_window: float = 0.3
```

`lsp_first_change_timeout` and `lsp_settle_window` are defaults for stacks that
leave the corresponding `LspStack` field at its built-in default; a non-default
per-stack value (for example from `lsp_servers_json`) wins.

Existing settings remain:

- `lsp_enabled=True`
- `lsp_servers_json=None`
- `lsp_initialize_timeout=10.0`
- `lsp_diagnostics_timeout=5.0`
- `lsp_failure_backoff_seconds=60.0`

`lsp_diagnostics_timeout` is the maximum wait for a request/wait. Per-stack
`settle` remains an upper bound but no longer forces the wait to its full value.

## Error handling and observability

- LSP failures never fail the write tool. The hook logs and returns `None`.
- `health()` data is available to the About endpoint but not shown in the UI in
  this phase.
- A stderr tail and last error are logged at warning level on start/transport
  failure.
- Success is logged at debug level: stack, root, sync generation, wait duration,
  number of diagnostics.

## Testing

### Fake server (`tests/fake_lsp_server.py`)

Add modes/behaviour:

- `--stderr-flood N`: write N lines to stderr interleaved with normal LSP
  responses; must not block.
- `--slow-init SECONDS`: delay the initialize response.
- `--no-publish`: accept `didOpen`/`didChange` but never publish.
- `--multi-publish`: publish an empty list, then an error, then an empty list.
- `--track-close`: record `didClose` URIs to a file for assertions.
- `--root-file`: on initialize, write the received `rootUri` to a file.

### Unit tests

- `test_lsp_detection.py`: pruned walk skips `node_modules/.venv/target`;
  detection works without traversal; `nearest_root` finds nested roots and
  falls back.
- `test_lsp_client.py`:
  - stderr flood does not hang and diagnostics still arrive;
  - two concurrent waits for the same path both complete;
  - a pre-change publish does not satisfy a post-change wait;
  - LRU eviction sends `didClose` and drops state;
  - slow init times out and sets `state="error"`.
- `test_lsp_manager.py`:
  - failure backoff is exponential and clears on success;
  - a dead server is stopped and replaced;
  - servers are keyed by `(nearest root, stack)`;
  - `active_for_session` exposes health.
- `test_lsp_hook.py`: still appends diagnostics for write tools, uses the
  nearest root, and skips non-code paths.

### Real servers

- Keep `test_lsp_real.py` but split initialization from measurement:
  - warm up with one write;
  - assert a clean Rust edit returns in < 2 s;
  - assert an erroneous edit returns a diagnostic.
- Add a stderr-heavy real Rust test only if it is stable locally; otherwise rely
  on the fake server.

## Out of scope

- Asynchronous delivery, on-demand tooling, and prompt reminders (Phase 2).
- UI changes.
- Project check commands.
- Hover/references/code actions.
- Incremental text sync.
- TCP/remote LSP and multi-root workspace folders beyond nearest-root selection.
