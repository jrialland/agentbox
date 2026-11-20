# Session Plan Tools (TODO-*) — Design

Date: 2026-11-19
Status: Approved (design), spec awaiting review.

## Goal

Give agents a persistent, session-scoped TODO list they can add to, update,
complete, reorder, inspect, and clear across turns, and show that plan to the
user in the chat above the conversation.

## Decisions

- **Granular tools** (`todo_add`, `todo_update`, `todo_complete`,
  `todo_remove`, `todo_reorder`, `todo_list`, `todo_clear`).
- **Normalized `PlanItem` table** (not a JSON column).
- **Always available** in every mode; planning is session state, not a
  filesystem write.
- **Collapsible Plan panel above the message list**, read-only.
- Poll while a run is active; refresh on completion.

## Data model

`agentbox_models/tables/core.py`:

```python
class PlanItem(SQLModel, table=True):
    id: str = Field(primary_key=True)            # 8-char hex
    session_id: str = Field(foreign_key="sessionrow.id", index=True)
    position: int = 0                            # 0-based order
    content: str
    status: str = "pending"                     # pending|in_progress|completed
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
```

Alembic revision `plan_items` (down_revision `c4f8e2a1b9d3`) creates
`planitem` with an index on `session_id`. No uniqueness on `position` (reorder
writes sequentially).

`runtime.delete_session_data` deletes the session's `PlanItem` rows.

## Tools

`packages/agentbox-api/src/agentbox_api/plan_tools.py`:

```python
PLAN_TOOL_NAMES = (
    "todo_add", "todo_update", "todo_complete",
    "todo_remove", "todo_reorder", "todo_list", "todo_clear",
)

def make_plan_tools(factory, session_id: str) -> dict[str, Callable]:
    ...
```

All tools are async and operate on the given session:

| Tool | Behaviour |
|---|---|
| `todo_add(content)` | Trim, require 1–500 chars; append at `max(position)+1`; id = `uuid4().hex[:8]` (retry on collision); returns `Added <id>: <content>` |
| `todo_update(item_id, content=None, status=None)` | Update content and/or status (content trimmed/capped); at least one field required; status must be a valid value; returns `Updated <id>` |
| `todo_complete(item_id)` | Set status `completed`; returns `Completed <id>` |
| `todo_remove(item_id)` | Delete and renumber remaining positions; returns `Removed <id>` |
| `todo_reorder(item_ids)` | Require each current id exactly once (no missing/extra/duplicates); write positions in the given order; returns `Reordered <n> items` |
| `todo_list()` | `TODO list is empty.` or a checklist (`[ ]`, `[~]`, `[x]`) with id, position and content |
| `todo_clear()` | Delete all items; returns `TODO list cleared` |

Unknown ids, invalid statuses, non-exactly-matching reorder sets and empty
content raise `pydantic_ai.ModelRetry` with a corrective message so the model
can retry (rather than failing the run).

## Wiring

`prepare_agent`:

- when `session_id` is present, merge `make_plan_tools(factory, session_id)` into
  `extra_tools` (alongside `activate_skill`);
- append `NativeToolBinding(name=...)` for each `PLAN_TOOL_NAMES` entry to the
  spec (deduplicated by native name), so `ToolRegistry.select_tools` includes
  them for every agent, including Ask mode;
- the tools are registered with `required_flags=()`.

Chat/ACP/A2A already pass a session id, so the tools are available everywhere.

## API

`GET /sessions/{sid}/plan` (`sessions:read`):

```json
{"items": [{"id": "a1b2c3d4", "position": 0, "content": "...", "status": "pending"}]}
```

Ordered by `position`; 404 when the session is unknown. No write endpoint
(tools own mutations).

## UI

`apps/web/src/chat/PlanPanel.tsx`:

- Renders nothing when the plan is empty.
- A collapsible card above the message list in `SessionPage`, expanded by
  default, showing each item's status badge and content.
- `useSessionPlan(sessionId, running)` polls every 2s while `chat.running`, then
  stops; `handleSend` invalidates `["session-plan", id]` after the run completes.
- Read-only.

## Tests

- `test_plan_tools.py`: add/list/update/complete/remove/reorder/clear; position
  compaction; invalid id/status/reorder/empty content → `ModelRetry`.
- `test_session_plan.py`: empty plan, ordered items, 404, permission.
- `test_plan_wiring.py`: `prepare_agent` adds all seven tools and binding names;
  they are selectable in Ask mode; `delete_session_data` removes items.
- `apps/web/src/chat/PlanPanel.test.tsx`: statuses/content rendering, collapse,
  and empty → no panel.
- No E2E: the test provider does not call tools; API/unit/component tests cover
  the flow.

## Out of scope

- User editing of the plan (tools own mutations).
- Plan history/versioning, cross-session plans, priorities/due dates.
- Streaming plan events (polling is used).
- Per-agent opt-in configuration (tools are always available).
