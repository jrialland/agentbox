# Sub-agent Sessions - Design

Date: 2026-11-20
Status: Approved (design), spec awaiting review.

## Goal

Let an agent start child agent sessions that run in the background, monitor
their status/output, wait for or cancel them, and nest further child sessions
up to a bounded depth. Child sessions are persisted, use the child agent's own
model/tools, and stay hidden from the normal project tree.

## Decisions

- **Persisted child sessions** in `SessionRow`, with status and parent link.
- **Hidden from the project tree**: `GET /sessions` returns top-level sessions
  only.
- **One unified starter**: `start_sub_session(agent, task, wait=False)`;
  background by default, synchronous with `wait=True`.
- **Monitoring tools**: `list_sub_sessions`, `get_sub_session`,
  `cancel_sub_session`.
- **Only configured sub-agents** (`spec.sub_agent_ids`) may be started.
- **Write-flag gated**: Ask mode cannot start child sessions.
- **Recursive** up to depth 3.
- **At most 5 running children per parent.**
- **Same project context** as the parent: project root, extra roots, skills,
  web settings, media limits, compaction config. Child mode is `agent`.
- **No new UI**; child sessions are visible through tool results only.

## Data model

`SessionRow` gains:

```python
parent_session_id: str | None = Field(
    default=None, foreign_key="sessionrow.id", index=True
)
sub_session_status: str | None = None   # running|completed|failed|cancelled
sub_session_error: str | None = None
sub_session_depth: int = 0
```

Alembic revision `sub_sessions` (down_revision `b2c3d4e5f6a7`) adds the four
columns. Normal sessions keep `parent_session_id=None`, a null status, and
depth 0.

The child's task is its first user turn. The child's latest assistant turn is
its output. `sub_session_status` and `sub_session_error` carry lifecycle state.

## Harness protocol and tools

`agentbox_harness/subagents.py`:

```python
class SubSessionRunner(Protocol):
    async def start(
        self,
        parent_session_id: str,
        parent_spec: AgentSpec,
        agent_name: str,
        task: str,
        wait: bool,
    ) -> str: ...

    async def list(self, parent_session_id: str) -> str: ...

    async def get(
        self, parent_session_id: str, sub_session_id: str, max_chars: int
    ) -> str: ...

    async def cancel(self, parent_session_id: str, sub_session_id: str) -> str: ...
```

`build_agent` adds the following tools when a runner is present, the spec has
`sub_agent_ids`, and the mode allows `write`:

| Tool | Behaviour |
|---|---|
| `start_sub_session(agent, task, wait=False)` | Validate the agent is configured; background returns the child id immediately; `wait=True` awaits completion and returns the output/error. |
| `list_sub_sessions()` | Child id, agent, status, depth, age, task summary. |
| `get_sub_session(sub_session_id, max_chars=4000)` | Status/agent/task plus latest assistant output or error, capped. |
| `cancel_sub_session(sub_session_id)` | Cancels a running child; reports if already finished. |

Tool failures (unknown agent, invalid task, limit reached, wrong parent) return
corrective strings, not `ModelRetry`.

The old synchronous `delegate_<agent>` tools remain available to harness users
that pass `sub_agents` directly, but the API uses the unified runner.

## API runner

`agentbox_api/subsessions.py` implements `ApiSubSessionRunner`:

- constructed by `prepare_agent` with the session factory, project root,
  skills directory, extra roots, web config, compaction config, media limits,
  and `sub_session_depth`;
- stores active tasks in a module-level registry keyed by child id;
- `start` prepares the child agent via `prepare_agent`, creates the child
  `SessionRow`, builds a child `Session`/`Harness`, and runs it with a local
  `EventBus`;
- on success, appends the assistant turn with `context_tokens` and sets
  `completed`; on failure sets `failed` + error; cancellation sets `cancelled`;
- `wait=True` awaits the wrapper and returns its result; `wait=False` returns
  immediately;
- `list`/`get`/`cancel` verify that the child's `parent_session_id` matches the
  caller's parent session.
- `get` and `list` reconcile a stale `running` row with no active task by
  marking it `failed` ("interrupted by backend restart").
- App startup marks any remaining `running` child rows as failed.
- `shutdown_sub_sessions` cancels all active wrappers.

Limits:

- `MAX_SUB_SESSIONS = 5` running children per parent.
- `MAX_SUB_SESSION_DEPTH = 3`; starting a child whose depth would exceed 3 is
  rejected (a depth-3 child cannot start further children).
- Starting a child increments the depth for its own recursive runner.

## Lifecycle and cleanup

- Parent session delete recursively cancels and deletes child sessions.
- ACP `close_session` cancels active child sessions but keeps their rows.
- Backend shutdown cancels all active child sessions.
- Child sessions remain hidden from `GET /sessions`; `GET /sessions/{sid}`
  still works when the id is known.

## Wiring

- `PreparedAgent` gains `sub_session_runner`.
- `prepare_agent` accepts `compaction` and `sub_session_depth`, builds the API
  runner lazily (to avoid a module cycle), and returns it.
- `Harness` accepts `sub_session_runner` and passes it plus the parent session
  id to `build_agent`.
- Chat, ACP, and A2A construct `Harness` with the runner and compaction config.
- Child `prepare_agent` calls use depth + 1 and the same project context.

## API and UI

- `GET /sessions` filters `parent_session_id IS NULL`.
- `SessionDetail` is unchanged; child detail remains fetchable by id.
- No frontend changes; child sessions are managed through tool calls.

## Tests

- Model/migration roundtrip for parent/status/error/depth fields.
- Harness tool gating: four tools only when sub-agents exist and mode allows
  write; absent in Ask mode.
- API runner:
  - background start → poll `get` → completed with output;
  - `wait=True` returns output synchronously;
  - unknown agent, empty task, active-limit, and depth-limit errors;
  - cancel running child;
  - stale `running` row with no task becomes failed;
  - parent delete removes child rows and cancels tasks;
  - `GET /sessions` hides child sessions.
- No new frontend tests.

## Out of scope

- A child-session browser or nested project-tree UI.
- Re-attaching to a child conversation from the UI.
- Cross-project children.
- Per-parent configurable concurrency/depth settings.
- Parent context injection of child transcripts beyond `get_sub_session`.

## Risks

- Background children consume model/tool resources; the 5-child/depth-3 limits
  bound the tree.
- Child rows survive backend restarts but their tasks do not; stale rows are
  marked failed.
- Deleting a parent recursively deletes child history.
- Child runs share the parent's project and extra roots; they are not sandboxed.
