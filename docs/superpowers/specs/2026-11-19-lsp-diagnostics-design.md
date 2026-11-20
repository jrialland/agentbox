# Automatic LSP Diagnostics — Design

Date: 2026-11-19
Status: Approved (design), spec awaiting review.

## Goal

Detect the language stacks used by a project (including subdirectories), keep a
language-server process alive per `(project, stack)`, and append file-scoped
diagnostics to `write_file`/`append_file`/`edit_file` results so the model can
fix errors it just introduced. A chat **About** panel shows which language
servers are active for the session.

## Decisions

- **Multi-stack**: start as many servers as there are distinct detected
  languages, not only the first stack.
- **Subdirectories count**: detection is recursive, with vendor/build folders
  pruned.
- **Lazy start**: a stack's server starts on the first matching file edit;
  detected-but-idle stacks are not started.
- **Shared per project**: one process per `(project_root, stack)`, reused across
  agents/sessions, shut down on app exit.
- **Pull-first diagnostics**, with `publishDiagnostics` fallback.
- **Lenient failures**: unavailable/crashed servers are logged and skipped; the
  file tool result is never failed by an LSP problem.
- **Real servers with availability skips** for integration tests, plus a fake
  stdio LSP server for deterministic protocol tests.

## Code layout

`packages/agentbox-harness/src/agentbox_harness/lsp/`:

- `stacks.py` — `LspStack`, defaults, extension/language mapping
- `detect.py` — recursive detection with pruning
- `client.py` — stdio JSON-RPC `LspServer`
- `manager.py` — shared `LspManager` singleton (with `reset()` for tests)
- `hooks.py` — `make_lsp_hook`

API integration lives in `agentbox-api` (`prepare_agent`, sessions About router).

## Stack definitions

`DEFAULT_LSP_SERVERS` is an ordered list; each entry:

```python
@dataclass(frozen=True)
class LspStack:
    name: str
    markers: list[str]      # glob patterns, relative to project root
    command: list[str]      # stdio command
    languages: list[str]    # LSP languageIds
    extensions: list[str]   # ".py", ".ts", ...
    pull: bool = True       # advertise/serve pull diagnostics
    save: bool = False      # send textDocument/didSave after syncing
    settle: float = 3.0     # wait after an empty publish for a follow-up
```

Defaults:

| Stack | Markers | Command | Extensions / languageIds |
|---|---|---|---|
| Python | `pyproject.toml`, `setup.py`, `requirements.txt`, `**/*.py` | `uvx ty server` | `.py`, `.pyi` / `python` |
| TypeScript/JS | `**/tsconfig.json`, `**/package.json` | `npx -y typescript-language-server@latest --stdio` | `.ts`, `.tsx`, `.js`, `.jsx` / `typescript`, `typescriptreact`, `javascript`, `javascriptreact` |
| Rust | `**/Cargo.toml` | `rust-analyzer` | `.rs` / `rust` |

> Rust uses `pull=False, save=True, settle=15`: rust-analyzer does not serve pull
> diagnostics in this setup and publishes only after `didSave`, first with an
> empty list and then with the real diagnostics. The client announces push-only,
> sends `didSave`, and keeps a short settle window for the follow-up publish.
>
> The TypeScript server needs a TypeScript 5.x installation in the project
> (`typescript` dev dependency); TypeScript 7 no longer ships `tsserver.js`.
> The integration test installs `typescript@5.9.3` into its temp workspace.
>
> `rust-analyzer` must be installed (e.g. `rustup component add rust-analyzer`);
> there is no zero-install runner equivalent to `uvx`/`npx`.

`lsp_servers_json` (settings) may replace this list with an array of the same
fields.

## Detection

`detect_stacks(project_root) -> list[LspStack]`:

- Walk the tree recursively with `os.walk`.
- Prune vendor/build/hidden directories: `.git`, `.venv`, `.venv-*`,
  `node_modules`, `target`, `dist`, `build`, `__pycache__`, and other hidden
  directories.
- For each stack, evaluate every marker with `glob.glob(str(root / marker),
  recursive=True)` semantics: a marker such as `**/*.py` matches at any depth.
- Return all stacks that have at least one match, in definition order.
- A stack is returned at most once, even with many matches.

`language_for(stack, path)` returns the stack's languageId for the file's
extension; a path with an unlisted extension is not handled by that stack.

## Process manager

`LspManager`:

- `detected(project_root) -> list[LspStack]` (cached per root).
- `get_or_start(project_root, stack) -> LspServer | None`:
  - returns the live server if present;
  - spawns + initializes otherwise;
  - on failure, records the failure and returns `None` for the next 60 s
    (configurable backoff), logging the reason;
  - removes and retries a server whose process died.
- `active_for_session(session_id) -> list[dict]` — stacks actually used by that
  session, each with `stack`, `command`, `root`, `status` (`starting`/`running`/
  `failed`), and `documents` (open-document count).
- `detected_for_project(project_root) -> list[str]` — stack names for the
  About panel.
- `reset()` — stop all servers and clear state (used by tests).
- `shutdown()` — stop every server (`shutdown` request, `exit` notification,
  terminate after a short grace period).

`configure_lsp(settings)` stores the enabled flag, stack overrides, and timeouts
and is called from the app lifespan and ACP entrypoint. The manager is a module
singleton so chat, ACP and A2A share per-project servers.

## LSP client

`LspServer` (one process, stdio):

- Spawn with `asyncio.create_subprocess_exec(*command, stdin=PIPE,
  stdout=PIPE, stderr=PIPE)`.
- **Framing**: `Content-Length: N\r\n\r\n` + JSON payload, per the LSP base
  protocol.
- Reader task:
  - resolves pending response futures by `id`;
  - records `textDocument/publishDiagnostics` per URI and wakes waiters;
  - answers server-to-client requests safely: `workspace/configuration` →
    per-item defaults, `client/registerCapability` → `None`,
    `window/showMessage` → log, `window/logMessage` → log, unknown → JSON-RPC
    method-not-found error;
  - a parse/transport error logs and marks the process dead.
- `initialize`: `rootUri`/`workspaceFolders` for the project root, capabilities
  advertising `publishDiagnostics` and `textDocument.diagnostic` (pull);
  `initialized` notification after the response.
- `sync_document(path)`: `didOpen` on first use (languageId, version 1, full
  text), `didChange` with full text and an incremented version on later writes.
- `diagnostics(path)`:
  - if the stack allows pull and the server advertised `diagnosticProvider`,
    request `textDocument/diagnostic` for the URI;
  - otherwise use push mode: `didSave` is sent when the stack requests it, and
    the client waits for a non-empty `publishDiagnostics` for that URI, allowing
    a short settle window after an empty publish;
  - normalize to `{line, character, severity, message, source}`; empty on
    timeout.
- `stop()`: `shutdown` request, `exit` notification, then terminate if needed.

Only stdio is supported; TCP/remote servers are out of scope.

## Hook

`make_lsp_hook(manager, session_id, project_root)` returns a `ToolHook`:

1. Only run for `ctx.tool_name in {"write_file", "append_file", "edit_file"}`.
2. Resolve the stacks detected for `project_root`; pick the stack whose
   extensions include the edited path's suffix. If none, return `None`.
3. `server = await manager.get_or_start(project_root, stack)`; on `None`,
   return `None`. On success, record the stack as active for `session_id`.
4. `await server.sync_document(path)` and `await server.diagnostics(path)`.
5. Format errors and warnings (severity 1/2), relative path, 1-based
   line:column, capped at 10 entries with an "and N more" note:

```
LSP diagnostics for src/main.py:
  4:8 error Name "x" is not defined (ty)
```

6. Return `None` when clean; hook exceptions are logged and swallowed.

`prepare_agent` passes `hooks=[make_lsp_hook(manager, session_id, project_root)]`
when `lsp_enabled` and `session_id` is available (chat/ACP/A2A already pass
`session_id` from D2).

## Settings

- `lsp_enabled: bool = True`
- `lsp_servers_json: str | None = None`
- `lsp_initialize_timeout: float = 10.0`
- `lsp_diagnostics_timeout: float = 5.0`
- `lsp_failure_backoff_seconds: float = 60.0`

## About API and panel

`GET /sessions/{sid}/lsp` (permission `sessions:read`):

```json
{
  "detected": ["python", "typescript"],
  "active": [
    {
      "stack": "python",
      "command": "uvx ty server",
      "root": "C:\\project",
      "status": "running",
      "documents": 3
    }
  ]
}
```

`SessionPage` gains an **About** button opening a modal that lists active
servers (stack, command, root, status, documents) and detected-idle stacks. The
handler resolves the session's project root from its `Project` row.

## Tests

### Unit
- `test_lsp_detection.py`: Python/TS/Rust markers, nested `**/*.py`, pruning
  `node_modules`/`.venv`, multiple stacks, extension→language mapping.
- `test_lsp_formatting.py`: severity filter, cap, clean output.

### Fake LSP over real stdio
`tests/fake_lsp_server.py` speaks Content-Length JSON-RPC and supports
initialize/didOpen/didChange/diagnostic/publishDiagnostics/shutdown.
- handshake + pull diagnostics with canned errors;
- didOpen then didChange with version increments;
- push fallback when no `diagnosticProvider`;
- diagnostics timeout when the server never answers;
- process crash → manager marks unavailable and later retries after backoff;
- clean shutdown (`shutdown` + `exit`).

### Hook and wiring
- `test_lsp_hook.py`: diagnostics appended for `write_file`, non-code paths and
  clean files skipped, hook errors isolated, active stacks recorded.
- `test_session_lsp.py`: About endpoint returns detected/active stacks for the
  session; permission required.
- `prepare_agent`/`build_registry` integration: a write to a code file appends
  diagnostics from the fake server.

### Real servers (availability-skipped, marked slow)
- Python: `uvx ty server` on a file with a deliberate error.
- TypeScript: `npx -y typescript-language-server@latest --stdio` with
  `typescript@5.9.3` installed in the workspace.
- Rust: `rust-analyzer` on a minimal Cargo crate (push mode + `didSave`).
Each asserts the returned text contains a diagnostic; skipped when the tool is
not on PATH. All three were verified locally (ty, TypeScript 5.9.3,
rust-analyzer 1.92).

### UI
E2E: open the About modal for a session and see the detected/active stack list.

## Out of scope / limits

- Eager server startup, code actions, definitions/references, formatting.
- Incremental edits (full-text sync only), TCP/remote LSP.
- Diagnostics for `delete_path` or non-code files.
- Multi-root workspaces (one project root per session).
- A diagnostics panel outside the chat About modal.
- Windows process-tree edge cases beyond terminate-on-exit.
