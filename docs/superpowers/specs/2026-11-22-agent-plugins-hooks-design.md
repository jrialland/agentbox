# Agent Plugin Hooks (D12b) — Design

Date: 2026-11-22
Status: Approved; implementation complete and verified.
Roadmap: D12b — full lifecycle plugin hooks via the `com.agentbox` client extension.
Depends on: D12a (`2026-11-22-agent-plugins-core-design.md`).

## Goal

Let an enabled Agent Plugin declare hooks in `com.agentbox/hooks/hooks.json` that
run on session, run, and tool events. Hooks may execute commands or HTTP calls,
inject context, mutate tool arguments, deny tool calls, replace tool results, and
observe errors. Hooks are disabled unless their plugin is enabled; enabling a
plugin is the explicit trust action for hooks.

## Decisions

- **Plugin enablement includes hooks.** No separate hook trust flag. The Plugins
  UI must warn clearly that enabling a plugin authorizes commands, HTTP calls,
  argument mutation, denial, and result replacement.
- **Declarative JSON, not executable plugin code.** Hooks are described in
  `com.agentbox/hooks/hooks.json`; actions are `command`, `http`, or static
  `context`. No Python imports or in-process plugin code.
- **Closed event set.** `session_start`, `session_end`, `run_start`, `run_end`,
  `run_error`, `before_tool`, `after_tool`, `tool_error`.
- **Map to pydantic-ai's capability hooks.** `before_run`/`after_run`/
  `on_run_error` and `before_tool_execute`/`after_tool_execute`/
  `on_tool_execute_error` are the execution seam.
- **Process-scoped session events.** `session_start` fires on the first run of a
  session in the current server process. `session_end` fires on session deletion
  or app shutdown. A server restart may fire `session_start` again.
- **Per-hook failure policy, default fail-open.** `on_error: ignore` (default)
  logs and continues; `on_error: deny` makes a failed `before_tool` hook deny the
  call. Hook failures never crash the run otherwise.
- **Hooks may replace tool results.** This is in scope alongside argument
  mutation and allow/deny. Replacement is model-visible and must be logged.
- **No sandboxing in this cycle.** Commands run as host subprocesses with
  timeouts, sanitized env, and path containment; D15 covers sandboxing.
- **No separate hook enablement per agent.** Hooks follow plugin enablement and
  project scope. Subagent sessions run their own hook lifecycle.
- **No new database state.** Hook state lives in plugin files; session-start
  tracking is in-memory runtime state. No migration.

## Hook package model

### File location

`<plugin>/com.agentbox/hooks/hooks.json`

Absent file means no hooks. A malformed file disables hooks for that plugin but
keeps its skills and MCP components; individual invalid hooks are skipped and
reported.

### Shape

```json
{
  "version": 1,
  "hooks": [
    {
      "id": "format-check",
      "event": "after_tool",
      "tools": ["write_file", "edit_file"],
      "action": {
        "type": "command",
        "command": "./scripts/check.sh",
        "args": ["--format"],
        "env": {"MODE": "ci"},
        "cwd": "${PLUGIN_ROOT}",
        "timeout_ms": 5000
      },
      "on_error": "ignore"
    },
    {
      "id": "deny-secrets",
      "event": "before_tool",
      "tools": ["write_file"],
      "action": {
        "type": "http",
        "url": "https://hooks.example.test/check",
        "method": "POST",
        "headers": {"X-Tenant": "public"},
        "timeout_ms": 2000
      },
      "on_error": "deny"
    }
  ]
}
```

Top-level fields are closed: `version` (required, must be 1) and `hooks`
(required array). Unknown top-level fields or a different version disable hooks
for the plugin.

Hook fields:

| Field | Type | Notes |
|---|---|---|
| `id` | string | Required, unique within the plugin, 1–64 chars. |
| `event` | enum | Required; one of the eight events. |
| `tools` | string[] | Optional; fnmatch patterns; only valid for tool events. Empty/omitted means all tools. |
| `action` | object | Required; exactly one of the command/http/context variants. |
| `on_error` | enum | `ignore` (default) or `deny`; `deny` only affects `before_tool`. |

Action variants:

- `command`: `command` (required, bare executable or `./` path inside plugin
  root), `args` (string[]), `env` (string map), `cwd` (`./`,
  `${PLUGIN_ROOT}`, or `${PLUGIN_DATA}`; default project root), `timeout_ms`.
- `http`: `url` (absolute HTTP(S), no userinfo/fragment; non-loopback must be
  HTTPS), `method` (default `POST`), `headers` (string map), `timeout_ms`.
- `context`: `text` (required static text).

Limits and validation:

- Max 50 hooks per plugin.
- `timeout_ms` defaults to 5,000 and is clamped to 100–30,000 for commands/HTTP.
- Hook ids unique; duplicate ids reject the duplicate hook.
- Command/cwd path containment and `${PLUGIN_ROOT}`/`${PLUGIN_DATA}` expansion
  follow the D12a MCP rules. `${PLUGIN_ROOT}`/`${PLUGIN_DATA}` are reserved env
  names and are injected by the runtime.
- Command stdin is JSON; stdout/stderr are capped at 64 KiB.
- HTTP response body is capped at 64 KiB; redirects are not followed.
- Injected context is capped at 8,000 characters per event.
- Unknown fields in a hook/action are validation errors for that hook; other
  hooks still load.

### Catalog integration

`PluginCatalog` loads hooks after skills/MCP and stores `LoadedPlugin.hooks`.
`PluginView` exposes a hook summary to the API/UI; no secrets are read from the
config. Hook issues use component names such as `com.agentbox:hooks` and
`com.agentbox:hook:<id>`.

## Runtime architecture

`packages/agentbox-api/src/agentbox_api/plugin_hooks.py`:

- `PluginHook` / `HookAction` models.
- `PluginHookRuntime` singleton with process-scoped session tracking.
- `PluginHooks(AbstractCapability)` implementing the pydantic-ai lifecycle hooks.
- `HookExecutor` for command/HTTP/static actions and response parsing.

### Capability mapping

| Event | pydantic-ai seam |
|---|---|
| `session_start` | `before_run` (once per session/process) |
| `run_start` | `before_run` (every run) |
| `run_end` | `after_run` |
| `run_error` | `on_run_error` |
| `before_tool` | `before_tool_execute` |
| `after_tool` | `after_tool_execute` |
| `tool_error` | `on_tool_execute_error` |

`prepare_agent` builds the capability with `session_id`, `project_id`,
`project_root`, enabled plugin hook sets, and plugin roots/data directories.
`Harness`/`build_agent` accept and attach it alongside existing capabilities.
Subagent sessions get an independent capability and session id.

### Session runtime

`PluginHookRuntime`:

- `started: set[str]` of session ids that fired `session_start` in this process.
- `active: dict[str, SessionHookSet]` used by `end_session` after the run
  capability is gone.
- `ensure_started(session_id, hooks, context)` runs `session_start` hooks once.
- `end_session(session_id)` runs `session_end` hooks and removes the session.
- `end_all()` runs `session_end` for every active session; called from app
  shutdown.
- `session_end` also runs from `delete_session_data` when a session is deleted.

Hooks are loaded at `prepare_agent`; a plugin disabled after a session started
does not retroactively remove hooks from that session.

### Hook context payload

Command stdin and HTTP body are one JSON object:

```json
{
  "event": "before_tool",
  "plugin": "acme-tools",
  "hook_id": "deny-secrets",
  "session_id": "s1",
  "project_id": "p1",
  "project_root": "C:\\repo",
  "run_id": "run-1",
  "tool_name": "write_file",
  "tool_call_id": "call-1",
  "args": {"path": "src/main.rs", "content": "..."},
  "result": "...",
  "error": {"type": "ToolFailed", "message": "..."},
  "plugin_root": "C:\\plugins\\acme-tools",
  "plugin_data": "C:\\plugins\\data\\acme-tools",
  "timestamp": "2026-11-22T23:00:00Z"
}
```

- `result` is a safe JSON representation; binary content becomes a descriptor
  with media type and size, not raw bytes.
- Tool args/results are truncated for the payload; the hook receives enough
  context to decide, not an unbounded transcript.
- No host secrets are included. Environment variables are not copied into the
  payload.

### Hook response contract

Command stdout and HTTP response bodies are parsed as:

- A JSON object with any of:
  - `decision`: `allow` or `deny` (`before_tool`; deny raises `ToolFailed`
    with `reason`);
  - `reason`: string used for denial/failure context;
  - `args`: replacement tool arguments (`before_tool`);
  - `result`: replacement tool result (`after_tool`/`tool_error`);
  - `context`: text appended/injected as described below.
- Anything else is treated as `context` text.
- Unknown JSON fields are ignored for forward compatibility.
- Non-zero command exit, non-2xx HTTP status, timeout, unreadable/invalid JSON,
  or an unsupported replacement type is a hook error.

### Effects

- `before_tool`:
  - `allow`/no decision continues; `args` replaces validated args for the call;
  - `deny` raises `ToolFailed(reason)` and short-circuits the call;
  - `context` is accumulated and appended to the tool result after execution.
- `after_tool`:
  - `result` replaces the model-visible result;
  - `context` is appended to the (possibly replaced) result.
- `tool_error`:
  - `result` recovers the call with a replacement result;
  - without `result`, `context` is appended to the original error message and
    surfaced as `ToolFailed`;
  - otherwise the original error is re-raised.
- `session_start`/`run_start`:
  - `context` is injected as request-scoped system context via
    `RunContext.enqueue(SystemPromptPart(..., scope="request"))`;
  - `session_start` context applies to the first run only; `run_start` context
    applies to that run.
- `session_end`/`run_end`/`run_error`:
  - side effects only; `decision`/`args`/`result`/`context` have no
    model-visible effect and are logged/ignored.

Result append preserves structured content where possible: a `ToolReturn` result
keeps its content attachments and appends context to its text; a string result is
concatenated. Replacing a result with a JSON value is model-visible; unsupported
replacement types are treated as a hook error.

### Ordering and limits

- Enabled plugins run in catalog order (global then project, sorted by plugin
  directory), hooks in JSON order.
- `before_tool` hooks run sequentially; each sees args updated by the previous.
  A deny stops the chain.
- `after_tool`/`tool_error` hooks run sequentially; each sees the result updated
  by the previous.
- `session_start`/`run_start` contexts concatenate in order.
- No background execution. A hook must finish or time out within its configured
  timeout. Default 5 s, max 30 s per hook; output/context caps as above.
- Concurrent runs may execute their own hooks concurrently; hook definitions
  are immutable.

### Failure policy

- `on_error: ignore` (default): log warning, continue with the original
  args/result; context from a failed hook is discarded.
- `on_error: deny`: for `before_tool`, raise `ToolFailed` with the failure
  reason; for other events, log and continue (deny has no meaning there).
- Invalid hook config is skipped at catalog load; it never executes.

### Logging

- Info: hook id, event, plugin, duration, outcome (`allow`/`deny`/`context`/
  `result`/`error`).
- Warning: timeouts, non-zero exits, non-2xx responses, invalid output,
  policy denials.
- Debug: sanitized payload and response, subject to truncation.
- Never log raw secrets or binary content.

## API and UI

- Plugin list/details include hook summaries: id, event, matcher, action type,
  command/URL, timeout, `on_error`.
- Plugins page table shows a hook count; details drawer lists every hook.
- Enable/trust confirmation explicitly warns that hooks can execute commands,
  call HTTP, mutate tool args, deny calls, and replace tool results.
- No new endpoints or permissions; hooks follow plugin enablement and project
  scope.
- No separate hook toggle. To disable hooks, disable the plugin.

## Settings

No new required settings. Runtime constants in v1:

- `PLUGIN_HOOKS_MAX_PER_PLUGIN = 50`
- `PLUGIN_HOOKS_DEFAULT_TIMEOUT_MS = 5_000`
- `PLUGIN_HOOKS_MAX_TIMEOUT_MS = 30_000`
- `PLUGIN_HOOKS_MAX_OUTPUT_BYTES = 64 * 1024`
- `PLUGIN_HOOKS_MAX_CONTEXT_CHARS = 8_000`

Per-hook timeout is configured in `hooks.json`.

## Security and failure handling

- Plugin enablement authorizes hooks; the UI warning must be explicit and
  visible before confirmation.
- Commands run without a shell; `command` is a single token or `./` path inside
  the plugin root. cwd defaults to the project root and may be `./`,
  `${PLUGIN_ROOT}`, or `${PLUGIN_DATA}` with containment checks.
- Environment is sanitized: a small base set (`PATH`, `PATHEXT`, `SystemRoot`,
  `WINDIR`, `HOME`, `USERPROFILE`, `TEMP`, `TMP`), configured hook env, and
  runtime-provided `PLUGIN_ROOT`, `PLUGIN_DATA`, `AGENTBOX_PROJECT_ROOT`,
  `AGENTBOX_SESSION_ID`, `AGENTBOX_RUN_ID`, `AGENTBOX_EVENT`, `AGENTBOX_TOOL_NAME`.
  No arbitrary host env passthrough.
- HTTP: no redirects, non-loopback HTTPS, no userinfo/fragment, fixed headers,
  timeout, response cap. Header values are visible package data; no secrets.
- Result replacements and argument mutations are trusted plugin actions; they
  are logged and validated for JSON shape, not semantically revalidated against
  tool schemas.
- Hooks never crash the run unless `on_error: deny` on `before_tool`.
- No sandboxing; commands run as the server user. D15 is the sandboxing
  follow-up.
- Invalid hooks are isolated; skills/MCP remain usable.

## Testing

### Hook config/catalog

- Valid full config; every event and action variant.
- Unknown top-level fields/version, unknown hook/action fields, duplicate ids,
  invalid matcher/event/timeout.
- Command/cwd path containment, placeholders, reserved env, URL/header rules.
- Invalid `hooks.json` disables hooks but keeps skills/MCP; invalid individual
  hook is skipped.
- PluginView hook summaries and issues.

### Executor

- Command JSON response, plain-text response, non-zero exit, timeout, output cap,
  env/cwd placeholders, stdin payload.
- HTTP JSON/text, non-2xx, timeout, redirect rejection, response cap, header
  validation.
- Static context action.
- Response parsing: decision/reason/args/result/context, malformed JSON, unknown
  fields.

### Capability/runtime

- `session_start` once per process, `session_end` on deletion/shutdown.
- `run_start` context injected per run; `run_end`/`run_error` side effects.
- `before_tool` allow/deny/args/context, short-circuit on deny.
- `after_tool` result replacement + context.
- `tool_error` recovery and context-as-failure.
- Ordering across plugins/hooks, matcher globs, multiple hooks per event.
- `on_error` ignore/deny behavior.
- Tool result serialization/replacement for string and `ToolReturn`.
- Disabled plugin hooks absent; subagent session independence.

### Integration/E2E

- Temp plugin with a command hook plus a fake HTTP hook.
- Enable plugin, run a session with a tool call; verify deny, argument mutation,
  result replacement, context injection, and session start/end.
- Disable plugin; next run has no hooks.
- App shutdown runs `end_all`.
- UI: hook count, details, trust warning.

### Checks

- `uv run ruff check --fix packages`
- `uv run ty check packages`
- `uv run pytest` per package
- `cd apps/web && bun run test && bun run build`

## Out of scope

- Separate per-plugin hook trust.
- Arbitrary Python/in-process hook code.
- Sandboxing (D15).
- Background/fire-and-forget hooks.
- Hook result streaming/progress UI.
- Hook marketplace/install.
- Per-agent hook overrides.
- Persistent `session_start` across server restarts.
- Model-request hooks (`before_model`/`after_model`).
- Custom ordering beyond catalog order + JSON order.

## References

- Agent Plugins v1.0.0: https://agent-plugins.org/specification
- Client extension namespaces: §8 of the specification.
- pydantic-ai capabilities/hooks:
  `.venv/Lib/site-packages/pydantic_ai/capabilities/hooks.py`
- pydantic-ai tool denial/error semantics: `ToolFailed`, `ModelRetry`.
- D12a spec: `2026-11-22-agent-plugins-core-design.md`.
- Existing agentbox surfaces:
  - `packages/agentbox-api/src/agentbox_api/plugin_catalog.py`
  - `packages/agentbox-api/src/agentbox_api/plugin_service.py`
  - `packages/agentbox-api/src/agentbox_api/skills.py`
  - `packages/agentbox-harness/src/agentbox_harness/agent_factory.py`
  - `packages/agentbox-harness/src/agentbox_harness/harness.py`
  - `packages/agentbox-harness/src/agentbox_harness/tools/registry.py`
  - `apps/web/src/pages/PluginsPage.tsx`
