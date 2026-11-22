# Subagent Session Orchestration - Design

Date: 2026-11-22
Status: Approved (design); spec awaiting review.
Supersedes: `2026-11-20-subagent-sessions-design.md` for agent selection,
monitoring, and tool vocabulary.

## Goal

Let any agent session start child sessions in the background using any agent
configuration, continue its own work while they run, and monitor, wait for, and
cancel those subagent sessions. The model manages sessions; subagents are the
configurations used to run them.

This removes the `sub_agent_ids` allow-list, adds agent discovery, closes the
monitoring gap with terminal-style management tools, and retires the unused
in-process `delegate_*` model.

## Domain vocabulary (mandatory)

The distinction is subtle and must stay explicit in every spec, plan, tool name,
description, test, and code identifier.

- **Agent** - a configuration record (`Agent` row / `AgentSpec`): model,
  instructions, tools, modes. An agent is not a live unit. It is not spawned and
  it does not run by itself.
- **Session** (or **agent session**) - a live instance of an agent configuration:
  project, message history, active run, status. Sessions are what run, persist,
  and are monitored.
- **Subagent** - the agent configuration selected by a parent session for a child
  session. It is a role, not a running thing.
- **Subagent session** - a child session spawned by a parent session, linked by
  `SessionRow.parent_session_id`. It runs the selected subagent configuration.

Canonical wording: "start a subagent session using an agent configuration".
Avoid "spawn an agent", "run a subagent", "impersonate an agent", and the
ambiguous shorthand `sub_session` in new material.

Tool names use the canonical noun phrase `subagent session` (plural
`subagent sessions`) and the singular stem `subagent_session` in snake_case
(for example, `list_subagent_sessions`).

| Tool | Meaning |
|---|---|
| `list_agents()` | List agent configurations available as subagents. |
| `start_subagent_session(subagent, task, wait=False)` | Start a subagent session using the named agent configuration. |
| `list_subagent_sessions()` | List this parent session's subagent sessions. |
| `get_subagent_session(subagent_session_id, max_chars=4000)` | Read status and live or final output. |
| `cancel_subagent_session(subagent_session_id)` | Cancel a subagent session and its descendants. |
| `wait_subagent_session(subagent_session_id, timeout=30)` | Wait for one subagent session to finish or time out. |
| `wait_subagent_sessions(subagent_session_ids, mode="all", timeout=60)` | Wait for all or any listed subagent sessions. |

Legacy names (`start_sub_session`, `list_sub_sessions`, `get_sub_session`,
`cancel_sub_session`, `delegate_<agent>`) are retired. Database columns use
`subagent_session_*`; the old `sub_session_*` columns and `agent.sub_agent_ids`
are removed by the migration described below.

## Current state and gap

The existing implementation already runs child sessions in parallel and outlives
the parent turn:

- `start_sub_session(..., wait=False)` creates a child `SessionRow`, launches the
  run with `asyncio.create_task`, and returns immediately.
- Children are real sessions with their own agent, project context, history,
  status, output, and depth.
- `list`, `get`, `cancel`, depth 3, and five running children per parent exist.
- Chat, ACP, A2A, and nested children all use the same API runner.

The gaps are:

1. Agent choice is restricted by `spec.sub_agent_ids` in the harness tools and
   again in the API runner.
2. There is no tool to discover available agent configurations.
3. Running subagent sessions have no live output; `get` only shows the final
   assistant text after completion.
4. Waiting is only available at start (`wait=True`); there is no wait-by-id or
   wait-all/any.
5. Cancelling a child does not recursively cancel its descendants.
6. The list has no age or duration.
7. The in-process `delegate_*` tools are a second, unreachable model that
   contradicts the session-centric model.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Any agent configuration in the database may be used as a subagent. | The user-facing unit is the session; agent configs are reusable templates. |
| D2 | Remove the `sub_agent_ids` allow-list from behavior, `AgentSpec`, the API payload, and the agent form, and drop the DB column in the same migration. | Eliminates the wrong mental model with no residual state. |
| D3 | Add `list_agents` for discovery. | With no allow-list, the model needs the catalog of agent configurations. |
| D4 | Keep depth 3 and five concurrent running children per parent. | Operational protection against runaway recursion and resource use, not a capability restriction. |
| D5 | Keep the whole subagent-session tool bundle behind the `write` mode flag. | Ask remains read-only; starting a child creates a write-capable `agent`-mode session. |
| D6 | Add a `SubagentSessionManager` modeled on `JobManager`. | One live-state owner for status, timings, output, wait, and cancellation; the DB remains the durable record. |
| D7 | Subscribe to the child `EventBus` and keep a rolling output buffer. | Delivers terminal-like live monitoring without persisting every delta. |
| D8 | Add `wait_subagent_session` and `wait_subagent_sessions` (`all`/`any`). | Lets the parent orchestrate efficiently inside one turn without busy polling. |
| D9 | Cancel recursively; parent close/delete/shutdown cancel the whole descendant tree. | Prevents orphaned grandchildren, matching terminal process-tree kills. |
| D10 | Delete `build_subagent_tool(s)`, `Harness.sub_agents`, and their tests. | One model only: sessions spawning sessions. |
| D11 | Do not restore the agent-form subagent picker. | Selection happens at runtime through tools, not in agent configuration. |
| D12 | No subagent-session UI in this iteration. | Terminal v1 also has no UI; the tools are the management surface. |
| D13 | Replace, do not layer: delete the old modules, symbols, tool names, and tests; no aliases, re-exports, shims, or dual paths. | Keeps exactly one understandable delegation implementation. |

## Rewrite and complete removal

This is a replacement of the subagent implementation, not an additive layer. The
old in-process "impersonation" path and the old sub-session naming must not
survive alongside the new mechanism. There are no aliases, re-exports, shims,
feature flags, or dual code paths.

Land the replacement as one coherent change. Do not stage it as "add the new path
now, remove the old path later"; the old path is deleted in the same change.
`delegate_*` has no replacement: it is removed, not emulated.

### Delete outright

- `build_subagent_tool` and `build_subagent_tools`.
- `Harness.sub_agents` (constructor argument and attribute) and every call site
  that passes or reads it.
- `agentbox_harness/subagents.py` after the session tools move to
  `agentbox_harness/subagent_sessions.py`; do not leave a re-export module.
- `agentbox_api/subsessions.py` after the runner, context, manager, and lifecycle
  helpers move to `agentbox_api/subagent_sessions.py`; do not leave a re-export
  module.
- The `_active` registry; its role is replaced entirely by
  `SubagentSessionManager`.
- The old tool names `start_sub_session`, `list_sub_sessions`,
  `get_sub_session`, and `cancel_sub_session`; no compatibility aliases.
- `sub_agent_ids` from `AgentSpec`, `AgentCreate`, `AgentRepository.load`/`save`,
  the agent form, onboarding, and tests, and drop `agent.sub_agent_ids` in the
  same migration.
- `tests/test_subagents.py` (the in-process impersonation tests).

### Rename by moving, then delete the old name

| Old | New |
|---|---|
| `agentbox_harness/subagents.py` | `agentbox_harness/subagent_sessions.py` |
| `agentbox_api/subsessions.py` | `agentbox_api/subagent_sessions.py` |
| `SubSessionRunner` | `SubagentSessionRunner` |
| `SubSessionContext` | `SubagentSessionContext` |
| `ApiSubSessionRunner` | `ApiSubagentSessionRunner` |
| `build_sub_session_tools` | `build_subagent_session_tools` |
| `make_sub_session_tools` | `make_subagent_session_tools` |
| `cancel_sub_sessions` | `cancel_subagent_sessions` |
| `shutdown_sub_sessions` | `shutdown_subagent_sessions` |
| `reconcile_running_sub_sessions` | `reconcile_running_subagent_sessions` |
| `MAX_SUB_SESSIONS` | `MAX_SUBAGENT_SESSIONS` |
| `MAX_SUB_SESSION_DEPTH` | `MAX_SUBAGENT_SESSION_DEPTH` |
| `sessionrow.sub_session_status` | `sessionrow.subagent_session_status` |
| `sessionrow.sub_session_error` | `sessionrow.subagent_session_error` |
| `sessionrow.sub_session_output` | `sessionrow.subagent_session_output` |
| `sessionrow.sub_session_depth` | `sessionrow.subagent_session_depth` |
| `tests/test_sub_sessions.py` | `tests/test_subagent_sessions.py` |
| `tests/test_sub_session_tools.py` | `tests/test_subagent_session_tools.py` |
| `tests/test_sub_session_wiring.py` | `tests/test_subagent_session_wiring.py` |

Renaming means the old name is gone, not deprecated. Update every import and call
site in the harness, API, chat, ACP, A2A, runtime helpers, and tests.

### Database migration

Add one Alembic revision that lands with the code rewrite:

- drop `agent.sub_agent_ids`;
- rename `sessionrow.sub_session_status` to `subagent_session_status`;
- rename `sessionrow.sub_session_error` to `subagent_session_error`;
- rename `sessionrow.sub_session_output` to `subagent_session_output`;
- rename `sessionrow.sub_session_depth` to `subagent_session_depth`.

Use `op.batch_alter_table` for SQLite compatibility. The revision's
`down_revision` is the current Alembic head at implementation time. The renames
preserve existing values. The downgrade renames the columns back and re-adds
`sub_agent_ids` as a non-null string with server default `'[]'`. Do not leave a
transition period where old and new columns coexist.

### No residue

After implementation, a repository search over runtime code must return no
matches for `delegate_`, `sub_agent_ids`, `sub_session`, `start_sub_session`,
`list_sub_sessions`, `get_sub_session`, `cancel_sub_session`,
`ApiSubSessionRunner`, `SubSessionRunner`, or `SubSessionContext`.

Allowed exceptions only:

- Alembic revisions, including the new migration that must reference the old
  column names;
- the migration regression test, which must assert that the old columns are gone;
- historical specs and plans that describe the previous design.

There must be exactly one delegation mechanism: a session starts a subagent
session. There is no in-process agent impersonation path.

## Tool contracts

All tools are added when a runner and parent session id are present and the mode
allows `write`. Failures return corrective strings, not `ModelRetry`. Every
id-based tool verifies that the target's `parent_session_id` matches the calling
session and otherwise returns `Subagent session not found.`

### `list_agents() -> str`

Returns the available agent configurations, sorted by name, one per line, with
`name` and `description`. Includes the current agent so a session can delegate to
another instance of its own configuration.

### `start_subagent_session(subagent: str, task: str, wait: bool = False) -> str`

- Rejects an empty task.
- Resolves `subagent` by name; unknown names return the available names.
- Rejects a depth that would exceed 3 and a sixth running direct child.
- Creates the child `SessionRow`, prepares the child agent with the parent's
  project root, extra roots, skills, web settings, media limits, and compaction
  config, then starts the run.
- Default is background: return the child session id immediately.
- `wait=True` awaits that child and returns its final status and output; it has no
  timeout, so use `wait_subagent_session` when a bounded wait is needed.

### `list_subagent_sessions() -> str`

Returns this parent session's child sessions, most recent first, with id,
subagent name, status, depth, age, duration when known, and a task summary. After
a restart, age is derived from the persisted creation time and duration may be
unknown. Task summaries are capped at 80 characters.

### `get_subagent_session(subagent_session_id: str, max_chars: int = 4000) -> str`

Returns status, subagent name, depth, age, task, and output. While running,
output is the live tail from the manager. After completion, it is the final
output or error. `max_chars` is clamped to 100..100000.

### `cancel_subagent_session(subagent_session_id: str) -> str`

Cancels the child and every descendant, awaits termination for up to 5 seconds,
and sets each row to `cancelled`. Reports when the target is already finished.

### `wait_subagent_session(subagent_session_id: str, timeout: int = 30) -> str`

Waits until the child reaches `completed`, `failed`, or `cancelled`, or the
timeout expires. Uses the live manager when present and falls back to the DB
status when the child is not live (for example, after a restart). Timeout is
clamped to 1..600 seconds. Returns the current status and output summary; timeout
is not an error.

### `wait_subagent_sessions(subagent_session_ids: list[str], mode: str = "all", timeout: int = 60) -> str`

Waits for all or any of the listed children. `mode` is `all` or `any`. Uses live
jobs when present and falls back to DB status otherwise. Returns a status/output
summary for each. Unknown ids are reported individually. Timeout returns current
statuses without raising.

## Architecture

### Harness tools

`agentbox_harness/subagents.py` becomes `agentbox_harness/subagent_sessions.py`
with:

```python
from collections.abc import Sequence


class SubagentSessionRunner(Protocol):
    async def list_agents(self) -> str: ...
    async def start(
        self,
        parent_session_id: str,
        subagent: str,
        task: str,
        wait: bool,
    ) -> str: ...
    async def list(self, parent_session_id: str) -> str: ...
    async def get(
        self,
        parent_session_id: str,
        subagent_session_id: str,
        max_chars: int,
    ) -> str: ...
    async def cancel(
        self, parent_session_id: str, subagent_session_id: str
    ) -> str: ...
    async def wait(
        self, parent_session_id: str, subagent_session_id: str, timeout: int
    ) -> str: ...
    async def wait_many(
        self,
        parent_session_id: str,
        subagent_session_ids: Sequence[str],
        mode: str,
        timeout: int,
    ) -> str: ...
```

- `build_subagent_session_tools(mode, runner, session_id)`, gated only by
  runner, session id, and `write` mode. It no longer reads a parent allow-list.
- `list_agents` and the start tool include clear descriptions that distinguish
  the agent configuration from the session.

`build_agent` removes `build_subagent_tools` and `sub_agents`; it adds the
subagent-session tools through the runner. `Harness` loses its `sub_agents`
field.

### API manager

`agentbox_api/subagent_sessions.py` replaces `subsessions.py` with:

- `SubagentSessionContext` - factory, project root, skills directory, extra
  roots, web config, compaction config, media limits, depth.
- `SubagentSessionJob` - id, parent id, subagent name, task, depth, status,
  `started_at`, `ended_at`, rolling output buffer, `asyncio.Task`, `Run`,
  completion `asyncio.Event`, result, and error.
- `SubagentSessionManager` - module-level singleton. Starts jobs, owns the live
  map keyed by child id, and exposes `jobs(parent_id)`, `get`, `output_text`,
  `wait`, `wait_many`, `cancel` (recursive), `cancel_children(parent_id)`,
  `shutdown`, and restart reconciliation. Descendants are discovered recursively
  through `SessionRow.parent_session_id` and the live map.
- `ApiSubagentSessionRunner` - protocol implementation used by `prepare_agent`.

Live output:

- Before starting the run, subscribe to the child `EventBus`.
- A drain task appends assistant text deltas and compact tool activity lines
  (`[tool] <name>: started|completed|failed`) to a rolling buffer capped at
  200000 characters, with a truncation marker.
- Thinking deltas are not included in the monitoring output.
- The drain task stops and the bus closes when the run terminates.
- `get_subagent_session` reads the live buffer while running; after completion
  the final output comes from the child's assistant turn and the
  `subagent_session_output` column.

Completion and persistence:

- On success, append the assistant turn with context tokens, set
  `SessionRow.subagent_session_status` to `completed`, cache the output in the
  `SessionRow.subagent_session_output` column, and set the completion event.
- On failure, set `subagent_session_status` to `failed` and
  `subagent_session_error`; on cancellation, set `cancelled`.
- The child session uses mode `agent` and the parent's project root, extra roots,
  skills, web settings, media limits, and compaction config.
- `list`/`get` fall back to the DB when no live job exists, and reconcile a stale
  `running` row with no job as `failed` ("interrupted by backend restart").
- App startup reconciles all remaining `running` child rows to `failed`.

Limits:

- `MAX_SUBAGENT_SESSIONS = 5` running direct children per parent.
- `MAX_SUBAGENT_SESSION_DEPTH = 3`.
- Starting a child increments the depth for its own runner.
- No global cap in this iteration.

### Removal of `sub_agent_ids`

- Remove `sub_agent_ids` from `AgentSpec`, `AgentCreate`, `AgentRepository.load`
  and `save`, the agent form state and submit payload, onboarding, and tests.
- Drop `agent.sub_agent_ids` and rename the `sessionrow.sub_session_*` columns in
  the same Alembic revision.
- Clients that still send the field are ignored.
- Regenerate `apps/web/openapi.json` and `apps/web/src/api/schema.d.ts` after the
  API model changes.

### Wiring and lifecycle

- `PreparedAgent` exposes `subagent_session_runner`.
- `prepare_agent` accepts `compaction` and `subagent_depth`, builds the API
  runner lazily, and returns it.
- Chat, ACP, A2A, and nested child preparation all pass the runner.
- Parent delete recursively cancels and deletes descendants.
- ACP `close_session` and app shutdown recursively cancel descendants.
- Child sessions remain hidden from `GET /sessions`; `GET /sessions/{id}` still
  works when the id is known.

## Testing

- Vocabulary/tool surface: only the new tool names are registered; the bundle is
  present in `write` mode without any parent allow-list; Ask mode registers none.
- Existing fixtures that set `sub_agent_ids` are updated or removed, and the
  generated OpenAPI artifacts are regenerated.
- Alembic migration: upgrade a DB at the previous revision (with
  `agent.sub_agent_ids` and `sessionrow.sub_session_*`), assert the dropped and
  renamed columns are correct and existing values are preserved, then downgrade
  and assert the old shape is restored.
- Frontend: remove the dead `subAgents` form state and payload, update component
  tests, and add no new UI.
- `list_agents` returns all seeded agent configurations, including the current
  agent.
- Start any agent by name; unknown names return the available names.
- Parallel monitoring with the `test_slow` provider:
  - start two children with `wait=False`;
  - parent work continues;
  - `get_subagent_session` shows partial text while a child is running;
  - `wait_subagent_sessions(mode="any")` returns when one finishes;
  - `wait_subagent_sessions(mode="all")` returns both outputs.
- `wait_subagent_session` timeout returns the current status without raising.
- Recursive cancel cancels children and grandchildren.
- Five-running-child limit and depth-3 limit.
- Manager tests use a fresh manager (or reset the singleton) so jobs do not leak
  between tests.
- Parent delete removes descendant rows and cancels tasks.
- Restart reconciliation marks stale running rows failed.
- `GET /sessions` hides child sessions.
- Residue check: the repository search in "No residue" returns no forbidden
  runtime symbols, and only one delegation mechanism exists.
- No new frontend tests beyond updating the existing agent-form component tests.

## Out of scope

- A subagent-session browser, project-tree nesting, or re-attach UI.
- Streaming child activity into the parent AG-UI stream as custom events.
- Usage/cost aggregation from children into the parent.
- Cross-project children.
- Per-parent configurable concurrency/depth.
- Backward compatibility for the old subagent tool names or old `sub_agent_ids`
  semantics; both are removed.
- Preserving old allow-list data; the dropped column is not migrated into any
  replacement field.
- Multi-tenant filtering of the agent catalog; this iteration exposes all agents
  to any session that can use the tools.

## Risks

- Any session can use any agent configuration, including more powerful models and
  tools. This is intentional; deployments that need tenant isolation must add a
  visibility filter later.
- Live output buffers consume memory; the 200000-character cap bounds each child.
- Background children consume model and tool resources; the five-child and
  depth-3 caps bound the tree.
- Child rows survive restarts but live tasks do not; stale rows are marked
  failed and retain their final output when available.
- Child runs share the parent's project and extra roots; they are not sandboxed.
- The migration is destructive: `agent.sub_agent_ids` values are lost, and
  existing databases must run the Alembic upgrade before the new code starts.

## References

- Previous design - `docs/superpowers/specs/2026-11-20-subagent-sessions-design.md`.
- Terminal job management - `docs/superpowers/specs/2026-11-20-terminal-design.md`,
  `packages/agentbox-harness/src/agentbox_harness/tools/terminal.py`.
- Harness delegation - `docs/superpowers/specs/2026-11-17-agentic-harness-design.md`.
- Vocabulary - `AGENTS.md`.
