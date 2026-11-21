# D22 - Stdio MCP Servers for Agents

- **Date:** 2026-11-22
- **Status:** Approved
- **Sub-project:** D22 - configure local stdio MCP servers on agents, with session-scoped process lifecycle.
- **Source:** the MCP row in [`docs/ROADMAP.md`](../../ROADMAP.md) and the product request to support local MCP servers alongside remote HTTP endpoints.
- **Roadmap:** `D22` in [`docs/ROADMAP.md`](../../ROADMAP.md).

## 1. Context and scope

Agentbox supports remote MCP servers configured as URL tool bindings. A partial stdio path already exists:

- `McpToolBinding` has `command`, `args`, and `env`.
- `build_mcp_toolset` builds a FastMCP `StdioTransport` when `command` is set.
- ACP `new_session`/`load_session`/`resume_session` merge client-provided stdio servers into a per-session spec.

However, stdio servers are not configurable in the agent UI, have no `cwd`, and are rebuilt on every agent run. Because `build_agent` creates a fresh `MCPToolset` per run, each turn spawns and kills the subprocess. Stateful local servers (for example a time or resource server) lose state between turns and pay startup cost repeatedly.

D22 makes stdio MCP servers first-class agent configuration and gives their processes the same lifetime as the session that uses them.

### 1.1 In scope

- Add `cwd` and `env_passthrough` to `McpToolBinding`.
- Session-scoped stdio MCP process manager in the harness.
- Spawn once on the session's first run, reuse across turns.
- Pin the effective stdio binding set on first use; agent edits apply to new sessions.
- Terminate on session delete/close, after an idle TTL, and on app shutdown.
- cwd defaults to the session project root; relative paths resolve against it; absolute paths are sandboxed to the project root or extra roots.
- Env merge from explicit values plus host pass-through names; never log values.
- Agent create and edit UI for remote-URL and stdio entries.
- `PUT /agents/{name}` and a frontend edit flow.
- MCP Apps relay support for stdio servers, using the session's running process.
- Shared manager integration for web, ACP, A2A, and sub-sessions.
- Warn-and-continue behavior when a server fails to start.
- A real integration test using `uvx mcp-server-time`.

### 1.2 Out of scope

- HTTP/SSE client-provided MCP servers in ACP (unchanged: stdio only is advertised).
- Per-session user-supplied MCP configuration outside ACP (agent definitions stay the source of truth for web sessions).
- Persisting the pinned binding set in the database.
- Automatic package installation for stdio commands.
- MCP server health monitoring beyond start failure and crash detection at call time.
- Denylist semantics for environment variables (host pass-through is an allowlist).
- Reworking remote URL MCP transport behavior.

### 1.3 Dependencies

- `pydantic_ai.mcp.MCPToolset` and `fastmcp.client.transports.StdioTransport` (already used).
- `MCPToolset.__aenter__`/`__aexit__` support nested entry and reference counting, so an externally held toolset stays connected while an agent run enters and exits it.
- MCP SDK `get_default_environment()` only inherits a safe allowlist (PATH, HOME/USERPROFILE, TEMP, and similar), so explicit env and `env_passthrough` do not leak other host variables.
- Existing `Project.path` / `Project.extra_roots` and the terminal's cwd sandbox logic.
- Existing `ToolRegistry`, `Harness`, `build_agent`, and AG-UI `CustomEvent` pass-through.
- No new Python dependency and no Alembic migration.

## 2. Goals and success criteria

- An agent author can add a local stdio MCP server (command, args, env, cwd) through the UI and through the API.
- A stdio server process starts once for a session and is reused across turns.
- The process's cwd defaults to the project workspace and can be narrowed to a subdirectory.
- Process cleanup is deterministic: session delete/close, idle TTL, and app shutdown all terminate processes.
- A broken server produces a visible warning and the rest of the agent still works.
- Remote URL MCP behavior is unchanged.
- Existing agents without MCP or with URL-only MCP continue to load and run identically.

## 3. Decisions and rationale

| # | Decision | Rationale |
|---|---|---|
| D1 | **Session-owned process manager in the harness.** | All run paths share one lifecycle implementation, close to the `Session` concept. |
| D2 | **Spawn lazily on the first run, not at session-row creation.** | Sessions can be created and never used; lazy start avoids idle processes. |
| D3 | **Pin stdio bindings on first use.** | Predictable behavior; mid-session edits cannot mutate a running process's configuration. |
| D4 | **Only stdio bindings are session-scoped; URL toolsets stay per run.** | Remote toolsets are cheap to construct and existing behavior is stable. |
| D5 | **cwd defaults to the project root and is sandboxed.** | Matches the filesystem/terminal safety model for agent-controlled processes. |
| D6 | **Explicit env plus host allowlist names.** | Common MCP config shape while avoiding full host environment inheritance. |
| D7 | **Warn and continue on startup failure.** | One broken optional server should not block the whole agent. |
| D8 | **Warnings surfaced as AG-UI custom events for web; logged for ACP/A2A.** | AG-UI already passes arbitrary custom events; other protocols have no warning frame. |
| D9 | **Edit applies to new sessions; existing sessions keep their pinned set.** | Avoids surprise process restarts mid-conversation. |
| D10 | **No DB schema change.** | `tool_bindings` is already serialized JSON; new fields round-trip through it. |

## 4. Data model

`McpToolBinding` in `packages/agentbox-harness/src/agentbox_harness/spec.py` becomes:

```python
@dataclass(frozen=True)
class McpToolBinding:
    server_url: str = ""
    tool_prefix: str = ""
    id: str = ""
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    env_passthrough: list[str] = field(default_factory=list)
    cwd: str = ""
```

- Exactly one of `server_url` and `command` must be non-empty.
- `id` is the stable server id used for relay routing and warnings.
  - Stdio entries require an explicit `id` (the UI calls it "Name").
  - URL entries may omit `id`; a slug of the URL is used for backward compatibility.
  - Ids must be unique within an agent.
- `args` entries are strings.
- `env` values are strings. Values are never logged.
- `env_passthrough` names must match `^[A-Za-z_][A-Za-z0-9_]*$`.
- `cwd` is optional. Empty means the project root.

`_parse_bindings` in `agentbox_models.repos.agents` already routes entries with `server_url` or `command` to `McpToolBinding`; unknown/new fields are accepted automatically.

No migration is required because `Agent.tool_bindings` is a text column containing JSON.

## 5. Runtime architecture

### 5.1 `McpSessionManager`

Create `packages/agentbox-harness/src/agentbox_harness/tools/mcp_session.py`.

```python
@dataclass(frozen=True)
class McpWarning:
    server_id: str
    message: str

@dataclass
class SessionToolsets:
    toolsets: list[MCPToolset]
    warnings: list[McpWarning]

class McpSessionManager:
    async def toolsets_for(
        self,
        session_id: str,
        bindings: list[McpToolBinding],
        project_root: str,
        extra_roots: list[str] | None = None,
    ) -> SessionToolsets: ...

    def touch(self, session_id: str) -> None: ...

    async def close_session(self, session_id: str) -> None: ...

    async def sweep_idle(self, ttl_seconds: float) -> None: ...

    async def close_all(self) -> None: ...

def get_mcp_session_manager() -> McpSessionManager: ...
def reset_mcp_session_manager() -> None: ...  # tests
```

Internal entry:

```python
@dataclass
class _SessionEntry:
    bindings: list[McpToolBinding]      # pinned
    toolsets: list[MCPToolset]          # entered
    warnings: list[McpWarning]
    last_used: float
    lock: asyncio.Lock
```

Behavior:

- `toolsets_for` filters to stdio bindings (`command` non-empty).
  - On the first call for a session, it acquires a per-session creation lock, then starts one `MCPToolset` per stdio binding concurrently with `asyncio.wait_for(..., timeout=mcp_start_timeout_seconds)`.
  - Each toolset is entered and held (`await toolset.__aenter__()`).
  - A start failure is logged and recorded as a warning; other servers still start.
  - The effective stdio binding list is pinned in the entry, including the empty list. A session that starts with no stdio servers therefore pins "no stdio servers", so a later agent edit cannot add one mid-session.
  - If the session already has an entry, the passed bindings are ignored and the pinned toolsets are returned.
  - Every call updates `last_used`.
  - Warnings are returned only by the call that created the entry; later calls return none, avoiding repeated toasts.
- Entries with no started toolsets are still tracked and expire through the idle sweep.
- `close_session` exits every entered toolset (`__aexit__`) and removes the entry; repeated calls are no-ops.
- `sweep_idle` closes entries whose `last_used` is older than the TTL.
- `close_all` closes all entries and is used at app shutdown.
- Logging includes session id, server id, command, and arg count only. It never includes `env` keys/values or `env_passthrough` values. Failure messages are truncated to a bounded length.

### 5.2 cwd and env resolution

Extract the terminal's cwd sandbox helper into a shared harness helper (for example `agentbox_harness/tools/paths.py`) and reuse it from the terminal and the MCP manager:

- root = resolved project root.
- allowed roots = project root plus `extra_roots`.
- empty cwd -> root.
- relative cwd -> root / cwd.
- absolute cwd -> itself.
- resolve the candidate and require it to equal an allowed root or be inside one; otherwise the server is skipped with a warning.

Env construction:

```python
merged = {name: os.environ[name] for name in binding.env_passthrough if name in os.environ}
merged.update(binding.env)
```

- Start the subprocess with `cwd=<resolved path>` and `env=merged or None`.
- `None` means the MCP SDK's safe default environment; an explicit dict is merged on top of that safe default by the SDK.
- Never log env contents.

### 5.3 Harness and agent wiring

- `Harness.__init__` accepts an optional `mcp_manager`; the default is `get_mcp_session_manager()`.
- `Harness.run`:
  1. Collects `McpToolBinding`s from `session.agent_spec.tool_bindings`.
  2. Calls `mcp_manager.toolsets_for(session.session_id, bindings, session.project_root, extra_roots)`.
  3. Passes the returned `SessionToolsets` to `build_agent`.
- `Session` needs the extra roots used for cwd validation. Add `extra_roots: list[str] = []` to `Session` and populate it at construction sites (web project, ACP project, A2A project, sub-sessions from the parent context).
- `build_agent` gains `stdio_toolsets: list[MCPToolset] | None = None`:
  - Remote URL bindings are built as today.
  - Stdio bindings are ignored when `stdio_toolsets` is provided; the provided toolsets are appended.
  - When `stdio_toolsets` is `None`, current per-run stdio behavior remains for harness unit tests and non-session callers.
  - Sub-agent builds receive the same `stdio_toolsets` list.
- `build_subagent_tools` threads `stdio_toolsets` through.

### 5.4 Cleanup integration

- `delete_session_data` (API) calls `mcp_manager.close_session(session_id)` before deleting rows, for the session and each child.
- ACP `close_session` calls the manager after cancelling the run.
- App lifespan:
  - Starts a periodic task every `mcp_sweep_interval_seconds` calling `sweep_idle(mcp_idle_ttl_seconds)`.
  - Cancels the task and calls `close_all()` on shutdown.
- The sweep task logs only counts.

## 6. API changes

### 6.1 Agent validation

`routers/agents._to_spec` validates MCP entries:

- exactly one transport;
- stdio ids present, valid, and unique;
- remote ids, when present, unique;
- args are strings;
- env is string-to-string;
- env pass-through names are valid identifiers;
- cwd is a non-empty string when provided.

Invalid input returns `400` with a field-specific message.

### 6.2 Update endpoint

Add:

```python
@router.put("/{name}", response_model=AgentSpec)
async def update_agent(
    name: str,
    body: AgentCreate,
    request: Request,
    _=Depends(require_permission("agents:create")),
): ...
```

- The path name is authoritative; the body name must match.
- Uses `AgentRepository.save`, which already upserts by name.
- Does not touch avatar fields or agent cards.
- Returns the saved spec, which includes the new bindings.

No other route changes. `GET /agents/{name}` remains the prefill source.

## 7. MCP Apps relay for stdio

`agentbox_api/mcp_relay.py`:

- Relay entry points accept `session_id` in addition to the spec.
- Resolve the project root and extra roots from `SessionRow` -> `Project` when needed.
- For a stdio server whose id matches a pinned session entry, use that entry's running toolset.
- If the session has no entry, call `toolsets_for` lazily with the current agent spec and touch it.
- For a remote server, keep building a per-call `MCPToolset(server_url, id=...)`.
- Touch the session entry on every relay call so active app tabs keep the process alive.
- Unknown server ids still raise `KeyError`, mapped to `404` by the router.

`routers/sessions.read_app_resource` and `call_app_tool` pass `sid` through.

## 8. Startup warnings

- Web chat calls `mcp_manager.toolsets_for(...)` before building the run and retains the warnings.
- `raw_events()` yields one pydantic-ai `CustomEvent(name="mcp.warning", value={"server": server_id, "message": message})` per warning before the agent events.
- pydantic-ai `AGUIEventStream` passes `CustomEvent` through as an AG-UI custom event.
- Frontend `useChat` handles `EventType.CUSTOM` with `name === "mcp.warning"` by showing a Mantine notification. The run continues.
- Warnings are also logged at `WARNING` level with server id and message.
- ACP and A2A log warnings only because their protocols have no warning frame.

## 9. Frontend

### 9.1 Editor

Replace the URL-only `AgentMcpEditor` with a structured editor:

- A list of MCP server entries.
- Per entry:
  - transport toggle: Remote URL or Local command;
  - Name (`id`), required for local entries;
  - Remote: URL;
  - Local: command, args (one per line), cwd;
  - env: key/value rows, values masked;
  - env pass-through: comma- or newline-separated names.
- Add/remove entry controls.
- Validation mirrors the API:
  - URL format for remote entries;
  - command required for local entries;
  - name required and unique for local entries;
  - env names valid;
  - cwd cannot be empty when the field is added.

### 9.2 Create and edit

- Generalize `AgentCreateDrawer` into an `AgentFormDrawer` with `mode: "create" | "edit"` and an optional loaded agent.
- Edit mode prefills name (read-only), description, instructions, model, tools, MCP entries, modes, and sub-agents from `GET /agents/{name}`.
- `AgentList` gets an Edit action that opens the drawer.
- Add `useUpdateAgent` calling `PUT /agents/{name}`.
- On success, invalidate the agents query and close the drawer.

### 9.3 Help

Update the `agent.mcp` help content to describe both transports, the cwd rule (default project root, sandboxed), env handling, and session-scoped lifecycle.

### 9.4 Generated API artifacts

After the route change:

```powershell
uv run python apps/web/scripts/gen-openapi.py
cd apps/web
bun run codegen
```

## 10. ACP and A2A

- `AgentboxAcpAgent` uses `get_mcp_session_manager()`.
- Client-provided stdio servers continue to be merged via `_with_servers`; their `cwd` is the ACP session `cwd` unless the binding sets one.
- `close_session` closes the manager entry.
- The first prompt starts and pins the session's server set. `load_session`/`resume_session` that target an already-running ACP session reuse that pin; a changed client `mcp_servers` list applies only after the session is closed and reopened. New sessions pin the list supplied at first prompt.
- A2A sessions use the manager through `Harness`; no A2A-specific configuration surface is added.

## 11. Settings

Add to `agentbox_api.config.Settings`:

| Setting | Default | Purpose |
|---|---|---|
| `mcp_idle_ttl_seconds` | `1800` | Close a session's MCP processes after this much inactivity. |
| `mcp_start_timeout_seconds` | `30` | Bound each server startup. |
| `mcp_sweep_interval_seconds` | `60` | How often the idle sweeper runs. |

## 12. Testing

### 12.1 Harness unit/integration tests

`packages/agentbox-harness/tests/test_mcp_session.py`:

- Lazy start once, reuse on later calls.
- Pinned bindings ignore later edits.
- Concurrent `toolsets_for` calls start once.
- Idle sweep closes and removes entries.
- `close_session` is idempotent.
- Startup failure records a warning and healthy servers still start.
- cwd resolution: default root, relative subdirectory, absolute inside root, absolute escape rejected with a warning.
- Env merge: explicit wins over pass-through; a capture logger asserts values never appear.
- `build_agent` uses provided stdio toolsets and still builds URL toolsets.
- Sub-agents receive the same toolsets.

Use a small fake stdio server script so these tests do not need the network.

### 12.2 Real `uvx mcp-server-time` integration test

Add an integration test (harness or API, whichever hosts the fake-server helper) that configures:

```python
McpToolBinding(
    id="time",
    command="uvx",
    args=["mcp-server-time"],
    cwd="",               # defaults to the temp project root
    env_passthrough=[],
)
```

The test:

1. Skips with `pytest.skip` when `shutil.which("uvx")` is `None`.
2. Starts the manager for a temporary project root with a startup timeout.
3. Skips with a clear reason if the server cannot be started (for example no network to fetch the package), because this is an external integration test.
4. Asserts the toolset exposes the `get_current_time` (and, when present, `convert_time`) tool.
5. Calls `get_current_time` with a known timezone and asserts a non-empty result.
6. Calls `toolsets_for` a second time and asserts the same toolset object/process entry is reused (no second entry).
7. Closes the session and asserts the entry is gone.

This test is the end-to-end proof that a real third-party stdio MCP server works with the session manager.

### 12.3 API tests

`packages/agentbox-api/tests`:

- `PUT /agents/{name}` round-trips stdio bindings.
- Validation rejects zero transports, both transports, duplicate ids, bad env names.
- Chat with a test stdio server exposes a tool and reuses the process across two turns.
- A broken server emits an `mcp.warning` custom event and the run still succeeds.
- Relay reads a `ui://` resource from a stdio server through the session process.
- Deleting a session closes its process.
- Idle TTL closes a process (with a small TTL override).

### 12.4 ACP tests

- A client-provided stdio server starts once and is reused across prompts.
- `close_session` stops it.

### 12.5 Frontend tests

- Editor validation for remote and local entries.
- Create and edit prefill/submit.
- `useChat` shows a notification for `mcp.warning` and keeps the run alive.

### 12.6 Checks

- `uv run pytest packages/agentbox-harness -q`
- `uv run pytest packages/agentbox-api -q`
- `uv run pytest packages/agentbox-models -q`
- `uv run pytest packages/agentbox-providers -q`
- `uv run ruff check --fix packages`
- `uv run ty check packages`
- `cd apps/web && bun run test && bun run build`

## 13. Compatibility and migration

- Existing URL-only agents continue to work; missing `id` still falls back to a URL slug.
- Existing ACP behavior is preserved, now with persistent processes.
- No database migration.
- Regenerate OpenAPI artifacts after the new route.
- `docs/ROADMAP.md` MCP row is updated to `DONE` once the feature lands.

## 14. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Process leaks | Idle sweeper, session delete/close hooks, app shutdown `close_all`, and a bounded TTL. |
| One broken server blocks a run | Warn-and-continue; failure is per server. |
| Secret leakage in logs | Never log env keys/values or pass-through values; log command/args count only. |
| Arbitrary command execution | Stdio servers run local commands; only users with the `agents:create` permission can configure them. The UI warns that commands run with the server process's privileges, and cwd is sandboxed. |
| cwd escape | Shared sandbox helper; rejected cwd skips the server with a warning. |
| Concurrent turns on one session | Per-session creation lock; MCPToolset reference counting supports nested entry; tool calls are handled by the client. |
| Windows command resolution | Rely on MCP SDK `get_windows_executable_command`; document `cmd /c` as a fallback if a `.cmd` shim is not resolved. |
| Sub-sessions spawning many processes | Each child session gets its own entry and is cleaned up with the session tree; idle TTL bounds leftovers. |

## 15. Implementation slices

1. Spec fields, shared cwd helper, `McpSessionManager`, harness wiring, settings.
2. Agent validation, `PUT /agents/{name}`, relay integration, cleanup hooks.
3. Warning custom events and frontend notification.
4. Structured MCP editor, create/edit drawer, update query.
5. ACP/A2A wiring and lifecycle tests.
6. Real `uvx mcp-server-time` integration test, codegen, help content, roadmap update.

## 16. Open questions

None. All prior open questions were resolved during brainstorming:

- session lifecycle: spawn once and reuse across turns;
- UI surface: create and edit agents;
- cwd: optional, sandboxed to project plus extra roots;
- env: explicit values plus host pass-through names;
- cleanup: delete/close, shutdown, and idle TTL;
- mid-session edits: pin config at session start;
- relay: stdio supported through the session process;
- ACP: share the manager;
- startup failure: warn and continue.
