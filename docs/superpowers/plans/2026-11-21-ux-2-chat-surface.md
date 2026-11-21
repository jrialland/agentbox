# UX-2 Chat Surface and Runtime UX — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** COMPLETE (2026-11-21). All 21 tasks implemented and verified.\n\n**Goal:** Rebuild the chat surface around an ordered AG-UI segment model, persist compact run activity, add cancellation/retry/errors/attachment downloads, and make Markdown, Mermaid, scrolling, and the composer production-quality.

**Architecture:** Backend adds JSON `activity`/`attachments` fields to turns, an active-run registry with cancellation, retry-without-duplicate-user-turn, AG-UI `RUN_ERROR` emission, and attachment download. Frontend replaces transient chat buffers with an ordered segment reducer, renders live segments in event order, shows persisted activity chips in history, and rebuilds the chat/composer/MCP split view with the UX-1 design system.

**Tech Stack:** React 19, TypeScript, Vite 8, Mantine 9, RemixIcon, pydantic-ai 2.69, FastAPI, SQLModel/Alembic, react-markdown + remark-gfm, highlight.js, mermaid, Playwright, Vitest, Storybook 10.6.8.

## Global Constraints

- UX-2 includes backend and frontend changes.
- Persisted activity is **summary-only**: tool name, status, duration; reasoning duration; run status/error. No full reasoning text, args, or results after reload.
- Attachment metadata persists on user turns; full bytes remain in `SessionAttachment`.
- Preserve true segment order from AG-UI events; never reorder or merge across kinds.
- Stop keeps partial output and persists a `cancelled` assistant turn.
- Retry replaces the failed/cancelled branch without a duplicate user turn.
- Markdown uses highlight.js; Mermaid renders only complete fenced blocks.
- Composer is icon-first, Enter sends, Shift+Enter newline, Send/Stop toggle.
- MCP apps use a resizable desktop split and a mobile sheet.
- Remove `legacy-chat.css`, the Bulma import, and the `bulma` dependency by the end.
- Keep existing auth, project, agent, provider, A2A, avatar, and MCP behaviors.
- Run checks from `apps/web` for frontend; use `uv` from repo root for backend.

---

### Task 1: Backend turn metadata + migration

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/session.py`
- Modify: `packages/agentbox-models/src/agentbox_models/tables/core.py`
- Modify: `packages/agentbox-models/src/agentbox_models/repos/message_log.py`
- Create: `packages/agentbox-models/alembic/versions/d4e5f6a7b8c9_chat_activity.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`
- Test: `packages/agentbox-models/tests/test_sqlite_message_log.py`
- Test: `packages/agentbox-api/tests/test_messages_activity.py`

**Interfaces:**
- Produces `Turn.activity: dict | None`, `Turn.attachments: list[dict] | None`.
- Produces `TurnRow.activity`/`TurnRow.attachments` JSON columns.
- Produces `MessageRead.activity`/`MessageRead.attachments`.

- [ ] **Step 1: Write failing model tests**

Add to `packages/agentbox-models/tests/test_sqlite_message_log.py`:

```python
@pytest.mark.asyncio
async def test_round_trips_activity_and_attachments(factory):
    store = SQLiteMessageLogStore(factory, "s1")
    turn = Turn(
        id="t1",
        role="assistant",
        content="answer",
        parent_id=None,
        activity={"status": "success", "reasoning_ms": 1200, "tools": []},
        attachments=[{"id": "a1", "filename": "note.txt", "media_type": "text/plain"}],
    )
    await store.append(turn)
    loaded = await store.get("t1")
    assert loaded.activity == turn.activity
    assert loaded.attachments == turn.attachments
```

Add `packages/agentbox-api/tests/test_messages_activity.py` with an authenticated history request that asserts `activity` and `attachments` appear in `GET /sessions/{sid}/messages` (use the existing app fixture patterns).

- [ ] **Step 2: Run tests to verify failure**

```powershell
uv run pytest packages/agentbox-models/tests/test_sqlite_message_log.py -q
uv run pytest packages/agentbox-api/tests/test_messages_activity.py -q
```

Expected: FAIL because the fields do not exist.

- [ ] **Step 3: Add fields to `Turn` and `TurnRow`**

In `session.py`:

```python
@dataclass(frozen=True)
class Turn:
    id: str
    role: str
    content: str
    parent_id: str | None
    context_tokens: int | None = None
    created_at: datetime | None = None
    activity: dict | None = None
    attachments: list[dict] | None = None
```

In `core.py` `TurnRow`:

```python
activity: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
attachments: list[dict] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
```

Import `JSON` and `Column` as needed.

- [ ] **Step 4: Persist and read the new fields**

Update `SQLiteMessageLogStore.append` to pass `activity=turn.activity`, `attachments=turn.attachments`; update `list_turns`/`get` to hydrate them.

Update `MessageRead` and `list_messages`:

```python
class MessageRead(BaseModel):
    id: str
    role: str
    content: str
    parent_id: str | None = None
    created_at: str
    activity: dict | None = None
    attachments: list[dict] | None = None
```

- [ ] **Step 5: Add the Alembic migration**

Create `d4e5f6a7b8c9_chat_activity.py` with `down_revision = "c3d4e5f6a7b8"`:

```python
def upgrade() -> None:
    with op.batch_alter_table("turnrow") as batch:
        batch.add_column(sa.Column("activity", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("attachments", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("turnrow") as batch:
        batch.drop_column("attachments")
        batch.drop_column("activity")
```

Run:

```powershell
uv run alembic -c packages/agentbox-models/alembic.ini upgrade head
```

- [ ] **Step 6: Run tests and commit**

```powershell
uv run pytest packages/agentbox-models/tests/test_sqlite_message_log.py -q
uv run pytest packages/agentbox-api/tests/test_messages_activity.py -q
git add packages/agentbox-harness packages/agentbox-models packages/agentbox-api
git commit -m "feat(api): add turn activity and attachment metadata"
```

---

### Task 2: Run activity collector and persistence

**Files:**
- Create: `packages/agentbox-api/src/agentbox_api/activity.py`
- Test: `packages/agentbox-api/tests/test_activity.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`

**Interfaces:**
- Consumes `Turn.activity`/`attachments`.
- Produces `RunActivityCollector.observe(event)` and `.summary(status, error=None)`.
- Produces assistant turn persistence for success/cancelled/error.

- [ ] **Step 1: Write failing collector tests**

```python
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartStartEvent,
    PartEndEvent,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)

def test_activity_collector_records_tools_and_reasoning():
    collector = RunActivityCollector()
    collector.observe(PartStartEvent(index=0, part=ThinkingPart(content="hmm")))
    collector.observe(PartEndEvent(index=0, part=ThinkingPart(content="hmm")))
    call = FunctionToolCallEvent(
        part=ToolCallPart(tool_name="read_text_file", args={}, tool_call_id="c1")
    )
    result = FunctionToolResultEvent(
        part=ToolReturnPart(
            tool_name="read_text_file",
            content="ok",
            tool_call_id="c1",
            outcome="success",
        )
    )
    collector.observe(call)
    collector.observe(result)
    summary = collector.summary("success")
    assert summary["status"] == "success"
    assert summary["reasoning_ms"] >= 0
    assert summary["tools"][0]["name"] == "read_text_file"
    assert summary["tools"][0]["status"] == "success"
```

- [ ] **Step 2: Run to verify failure**

```powershell
uv run pytest packages/agentbox-api/tests/test_activity.py -q
```

Expected: FAIL because `RunActivityCollector` does not exist.

- [ ] **Step 3: Implement the collector**

`activity.py`:

```python
import time
from dataclasses import dataclass, field

from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    ThinkingPart,
    ThinkingPartDelta,
)


@dataclass
class ToolActivity:
    name: str
    started_at: float
    status: str = "success"
    ended_at: float | None = None


@dataclass
class RunActivityCollector:
    started_at: float = field(default_factory=time.monotonic)
    reasoning_started_at: float | None = None
    reasoning_ms: int = 0
    tools: dict[str, ToolActivity] = field(default_factory=dict)
    text: str = ""

    def observe(self, event) -> None:
        now = time.monotonic()
        if isinstance(event, PartStartEvent) and isinstance(event.part, ThinkingPart):
            if self.reasoning_started_at is None:
                self.reasoning_started_at = now
        if isinstance(event, PartDeltaEvent) and isinstance(event.delta, ThinkingPartDelta):
            if self.reasoning_started_at is None:
                self.reasoning_started_at = now
        if isinstance(event, PartEndEvent) and isinstance(event.part, ThinkingPart):
            if self.reasoning_started_at is not None:
                self.reasoning_ms += int((now - self.reasoning_started_at) * 1000)
                self.reasoning_started_at = None
        if isinstance(event, FunctionToolCallEvent):
            self.tools[event.tool_call_id] = ToolActivity(
                name=event.part.tool_name, started_at=now
            )
        if isinstance(event, FunctionToolResultEvent):
            tool = self.tools.get(event.tool_call_id)
            if tool is not None:
                tool.ended_at = now
                outcome = getattr(event.part, "outcome", "success")
                tool.status = "success" if outcome == "success" else "error"

    def summary(self, status: str, error: dict | None = None) -> dict:
        reasoning_ms = self.reasoning_ms
        if self.reasoning_started_at is not None:
            reasoning_ms += int((time.monotonic() - self.reasoning_started_at) * 1000)
        return {
            "status": status,
            "reasoning_ms": reasoning_ms,
            "tools": [
                {
                    "name": tool.name,
                    "status": tool.status,
                    "duration_ms": int(
                        ((tool.ended_at or time.monotonic()) - tool.started_at) * 1000
                    ),
                }
                for tool in self.tools.values()
            ],
            "error": error,
        }
```

- [ ] **Step 4: Integrate collector and persistence in `sessions.py`**

In `chat`, create the collector before the event loop, observe each `re.event`, and pass partial text to the finish path. In `finish()`:

```python
outcome = await run.await_outcome()
result = None
if outcome.status == "success":
    result = await run.await_result()
    content = str(result.output)
    context_tokens = context_tokens_from_usage(result.response.usage)
else:
    content = collector.text
    context_tokens = None
activity = collector.summary(
    outcome.status,
    {"code": outcome.code, "message": outcome.message} if outcome.status == "error" else None,
)
turn = Turn(
    id=uuid.uuid4().hex,
    role="assistant",
    content=content,
    parent_id=session.head_id,
    context_tokens=context_tokens,
    activity=activity,
)
await session.append(turn, parent_id=session.head_id)
```

`collector.text` should be appended from `TextPart` starts/deltas. Add to `observe`:

```python
from pydantic_ai.messages import TextPart, TextPartDelta
if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
    self.text += event.part.content
if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
    self.text += event.delta.content_delta
```

For the success path, prefer `result.output` over collected text. For cancelled/error, use collected text.

- [ ] **Step 5: Persist user attachment metadata**

Before the run, query attachment rows and build `attachments = [{"id": a.id, "filename": a.filename, "media_type": a.media_type} for a in arows]`. Pass them to the harness user turn (Task 3 adds `attachments`/`record_user_turn`). Until then, update the latest user turn after run as a temporary bridge; Task 3 replaces it with the harness parameter.

- [ ] **Step 6: Add success/cancel/error persistence tests**

Test success with tool activity, cancelled with partial text, and error with `activity.error` persisted.

- [ ] **Step 7: Run tests and commit**

```powershell
uv run pytest packages/agentbox-api/tests/test_activity.py -q
uv run pytest packages/agentbox-api/tests/test_messages_activity.py -q
git add packages/agentbox-api packages/agentbox-harness
git commit -m "feat(api): persist run activity summaries"
```

---

### Task 3: Retry without duplicate user turns + user attachment metadata

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/harness.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/session.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`
- Test: `packages/agentbox-harness/tests/test_harness_e2e.py`
- Test: `packages/agentbox-api/tests/test_retry_turn.py`

**Interfaces:**
- `Harness.run(..., record_user_turn: bool = True, user_attachments: list[dict] | None = None)`.
- `MessageRequest.retry_turn_id: str | None = None`.
- `Turn.attachments` persisted on user turns.

- [ ] **Step 1: Write failing retry test**

Create a session with user turn U and failed assistant turn A (A.parent_id=U). POST `/sessions/{sid}/messages` with `{content:"same", retry_turn_id:A.id}`. Assert:
- exactly one user turn with that content exists;
- the new assistant turn's `parent_id` is U.id;
- the old A branch is no longer the active leaf.

- [ ] **Step 2: Add harness parameters**

```python
async def run(
    self,
    session: Session,
    user_message: str,
    bus: EventBus,
    model_override=None,
    prompt_override=None,
    record_user_turn: bool = True,
    user_attachments: list[dict] | None = None,
) -> Run:
    ...
    if record_user_turn:
        turn = Turn(
            id=uuid.uuid4().hex,
            role="user",
            content=user_message,
            parent_id=session.head_id,
            attachments=user_attachments,
        )
        await session.append(turn, parent_id=session.head_id)
        user_turn_id = turn.id
    else:
        user_turn_id = session.head_id
    ...
```

The initial `message_history` must still be built after head selection; when `record_user_turn=False`, `session.head_id` already points to the existing user turn.

- [ ] **Step 3: Resolve `retry_turn_id` in `chat`**

```python
if body.retry_turn_id:
    async with factory() as s:
        retry_row = await s.get(TurnRow, body.retry_turn_id)
    if retry_row is None:
        raise HTTPException(status_code=404, detail="Retry turn not found")
    prompt_turn = retry_row
    if retry_row.role == "assistant":
        parent = await store.get(retry_row.parent_id) if retry_row.parent_id else None
        prompt_turn = parent
    if prompt_turn is None or prompt_turn.role != "user":
        raise HTTPException(status_code=400, detail="Retry turn has no user parent")
    session.head_id = prompt_turn.id
    body.content = prompt_turn.content
    record_user_turn = False
else:
    record_user_turn = True
```

Pass `record_user_turn` and `user_attachments` to `harness.run`.

- [ ] **Step 4: Persist attachments on the user turn**

`user_attachments` is the metadata list from Task 2. The harness stores it on the `Turn`.

- [ ] **Step 5: Run tests and commit**

```powershell
uv run pytest packages/agentbox-harness/tests/test_harness_e2e.py -q
uv run pytest packages/agentbox-api/tests/test_retry_turn.py -q
git add packages/agentbox-harness packages/agentbox-api
git commit -m "feat(api): retry turns without duplicate user messages"
```

---

### Task 4: Run registry and cancellation endpoint

**Files:**
- Create: `packages/agentbox-api/src/agentbox_api/runs.py`
- Test: `packages/agentbox-api/tests/test_cancel_run.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`

**Interfaces:**
- `RunRegistry.register(session_id, run)`, `.cancel(session_id) -> bool`, `.finish(session_id)`.
- `POST /sessions/{sid}/messages/cancel` -> 202 `{status:"cancelling"}` or 409.

- [ ] **Step 1: Write failing cancel tests**

Test 202 while a fake run is registered, 409 when idle, and that `run.cancel()` is called. Add an end-to-end test with a slow test model if available; otherwise assert registry behavior and the endpoint contract.

- [ ] **Step 2: Implement the registry**

```python
class RunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, object] = {}

    def register(self, session_id: str, run: object) -> None:
        self._runs[session_id] = run

    def cancel(self, session_id: str) -> bool:
        run = self._runs.get(session_id)
        if run is None:
            return False
        run.cancel()
        return True

    def finish(self, session_id: str) -> None:
        self._runs.pop(session_id, None)
```

- [ ] **Step 3: Register/cleanup and add the route**

In `chat`, after `harness.run`:

```python
registry = request.app.state.run_registry
registry.register(sid, run)
```

In `finish()`, call `registry.finish(sid)` in a `finally`. In `raw_events` finally, also call `registry.finish(sid)`.

Route:

```python
@router.post("/{sid}/messages/cancel")
async def cancel_message(sid: str, request: Request,
                         _=Depends(require_permission("sessions:create"))):
    if request.app.state.run_registry.cancel(sid):
        return {"status": "cancelling"}
    raise HTTPException(status_code=409, detail="No active run")
```

- [ ] **Step 4: Run tests and commit**

```powershell
uv run pytest packages/agentbox-api/tests/test_cancel_run.py -q
git add packages/agentbox-api
git commit -m "feat(api): add chat run cancellation"
```

---

### Task 5: Emit AG-UI RUN_ERROR for failures

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`
- Modify: `packages/agentbox-api/src/agentbox_api/streaming.py`
- Test: `packages/agentbox-api/tests/test_stream_error.py`

**Interfaces:**
- Normalized failures reach the AG-UI client as `RUN_ERROR`.
- `RunActivityCollector` still persists the error summary.

- [ ] **Step 1: Write a failing stream test**

Use the existing `test_tool`/test provider setup to force a `ModelAuthenticationError` (invalid API key) and assert the SSE body contains `RUN_ERROR` and the error message.

- [ ] **Step 2: Raise after the event stream ends**

In `raw_events` after the `async for` loop:

```python
outcome = await run.await_outcome()
if outcome.status == "error":
    raise RuntimeError(outcome.message or "Agent run failed")
if outcome.status == "cancelled":
    return
```

Do not double-raise for success. `AGUIEventStream.on_error` turns this into `RUN_ERROR`; `on_cancelled` emits no error.

- [ ] **Step 3: Verify cancellation remains clean**

A cancelled run should end the stream without `RUN_ERROR`, and the assistant turn should be persisted as `cancelled`.

- [ ] **Step 4: Run tests and commit**

```powershell
uv run pytest packages/agentbox-api/tests/test_stream_error.py -q
uv run pytest packages/agentbox-api/tests/test_cancel_run.py -q
git add packages/agentbox-api
git commit -m "fix(api): emit run errors to the AG-UI client"
```

---

### Task 6: Attachment download endpoint

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`
- Test: `packages/agentbox-api/tests/test_attachment_download.py`

**Interfaces:**
- `GET /sessions/{sid}/attachments/{aid}` returns bytes with filename/media type.
- 404 for missing or cross-session attachments.

- [ ] **Step 1: Write failing download tests**

Upload an attachment, download it, assert bytes/content type/`Content-Disposition`; request it from another session and assert 404.

- [ ] **Step 2: Add the route**

```python
@router.get("/{sid}/attachments/{aid}")
async def download_attachment(
    sid: str, aid: str, request: Request,
    _=Depends(require_permission("sessions:read")),
):
    async with request.app.state.session_factory() as s:
        row = await s.get(SessionAttachment, aid)
    if row is None or row.session_id != sid:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(
        content=row.data,
        media_type=row.media_type,
        headers={"Content-Disposition": f'inline; filename="{row.filename}"'},
    )
```

Import `Response`.

- [ ] **Step 3: Run tests and commit**

```powershell
uv run pytest packages/agentbox-api/tests/test_attachment_download.py -q
git add packages/agentbox-api
git commit -m "feat(api): add attachment download endpoint"
```

---

### Task 7: Ordered segment reducer

**Files:**
- Create: `apps/web/src/chat/segments.ts`
- Test: `apps/web/src/chat/segments.test.ts`

**Interfaces:**
- `Segment` union from the spec.
- `segmentReducer(state, action)` actions: `text-start`, `text-delta`, `text-end`, `reasoning-start`, `reasoning-delta`, `reasoning-end`, `tool-start`, `tool-args`, `tool-end`, `tool-result`, `app`, `reset`, `finalize`.
- `finalizeSegments(segments, status)` marks streaming segments done/cancelled.

- [ ] **Step 1: Write failing order tests**

```ts
import { describe, expect, it } from "vitest";
import { applyAgUiEvent, emptySegments } from "./segments";

describe("segment order", () => {
  it("keeps reasoning, tool, reasoning, text order", () => {
    let state = emptySegments();
    state = applyAgUiEvent(state, { type: "REASONING_MESSAGE_START", messageId: "r1" });
    state = applyAgUiEvent(state, { type: "REASONING_MESSAGE_CONTENT", messageId: "r1", delta: "hmm" });
    state = applyAgUiEvent(state, { type: "REASONING_MESSAGE_END", messageId: "r1" });
    state = applyAgUiEvent(state, { type: "TOOL_CALL_START", toolCallId: "c1", toolCallName: "list_directory" });
    state = applyAgUiEvent(state, { type: "TOOL_CALL_RESULT", toolCallId: "c1", content: "ok" });
    state = applyAgUiEvent(state, { type: "REASONING_MESSAGE_START", messageId: "r2" });
    state = applyAgUiEvent(state, { type: "REASONING_MESSAGE_CONTENT", messageId: "r2", delta: "again" });
    state = applyAgUiEvent(state, { type: "REASONING_MESSAGE_END", messageId: "r2" });
    state = applyAgUiEvent(state, { type: "TEXT_MESSAGE_START", messageId: "t1" });
    state = applyAgUiEvent(state, { type: "TEXT_MESSAGE_CONTENT", messageId: "t1", delta: "answer" });
    expect(state.map((s) => s.kind)).toEqual(["reasoning", "tool", "reasoning", "text"]);
    expect(state[3]).toMatchObject({ kind: "text", text: "answer" });
  });
});
```

Add tests for unknown ids, multiple text messages, result before text, and finalize cancel/error.

- [ ] **Step 2: Run to verify failure**

```powershell
bun run test -- src/chat/segments
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement the reducer**

Use a discriminated union and id-keyed updates:

```ts
export type Segment =
  | { id: string; kind: "reasoning"; text: string; status: "streaming" | "done"; startedAt: number; endedAt?: number }
  | { id: string; kind: "tool"; toolCallId: string; name: string; args: string; result?: string; status: "running" | "success" | "error"; startedAt: number; endedAt?: number }
  | { id: string; kind: "text"; messageId: string; text: string; status: "streaming" | "done" }
  | { id: string; kind: "app"; messageId: string; tab: AppTab };
```

`applyAgUiEvent` appends only on `*_START` and maps by `messageId`/`toolCallId` for deltas/results. Ignore unknown ids. `resetSegments` returns `[]`.

- [ ] **Step 4: Run tests and commit**

```powershell
bun run test -- src/chat/segments
git add apps/web/src/chat/segments.ts apps/web/src/chat/segments.test.ts
git commit -m "feat(web): add ordered chat segment reducer"
```

---

### Task 8: Wire the segment reducer into useChat

**Files:**
- Modify: `apps/web/src/chat/useChat.ts`
- Test: `apps/web/src/chat/useChat.test.tsx`

**Interfaces:**
- `useChat` exposes `segments`, `running`, `error`, `runStatus`, `appTabs`, `send`, `cancel`, `reset`, `closeApp`.
- `send` accepts `retryTurnId?: string`.

- [ ] **Step 1: Write failing useChat test**

Use a fake `createChatAgent` whose `runAgent` invokes the provided callbacks with interleaved events; assert the resulting `segments` order and that `running` is false after `RUN_FINISHED`.

- [ ] **Step 2: Replace state with the reducer**

```ts
const [segments, setSegments] = useState<Segment[]>([]);
const [running, setRunning] = useState(false);
const [error, setError] = useState<string | null>(null);
...
onTextMessageContentEvent: (p) => setSegments((s) => applyAgUiEvent(s, { type: "TEXT_MESSAGE_CONTENT", messageId: p.messageId, delta: p.textMessageBuffer })),
```

Note: the AG-UI client callback payloads use buffers; dispatch START/CONTENT/END events based on the callbacks that are available. If only buffer callbacks exist, derive deltas by tracking previous buffer lengths per id. The reducer must receive ordered events; use a stable segment id per message/tool.

- [ ] **Step 3: Add cancel**

```ts
async function cancel() {
  await fetch(`${baseUrl}/sessions/${sessionId}/messages/cancel`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  setRunStatus("cancelling");
}
```

`send` sets `runStatus="running"`; `RUN_FINISHED` sets `idle`; errors set `error`.

- [ ] **Step 4: Run tests and commit**

```powershell
bun run test -- src/chat/useChat.test.tsx
git add apps/web/src/chat/useChat.ts apps/web/src/chat/useChat.test.tsx
git commit -m "feat(web): use ordered segments in chat state"
```

---

### Task 9: Markdown stylesheet + highlight.js + copy

**Files:**
- Modify: `apps/web/package.json`
- Create: `apps/web/src/chat/markdown.css`
- Modify: `apps/web/src/chat/MarkdownBlock.tsx`
- Test: `apps/web/src/chat/MarkdownBlock.test.tsx`

**Interfaces:**
- `MarkdownBlock` renders styled headings/lists/tables/code with copy buttons.
- Code blocks use highlight.js and a custom token theme.

- [ ] **Step 1: Add highlight.js**

```powershell
cd apps/web
bun add highlight.js
```

- [ ] **Step 2: Write failing render tests**

Assert `h1`, `table`, `ul` and `pre > code` render, and the copy button copies the source.

- [ ] **Step 3: Implement styles and highlighting**

`markdown.css` defines `.markdown-block` typography, tables, blockquotes, code blocks, and `.hljs-*` token colors using `--ab-*` variables. `MarkdownBlock` uses `rehype-highlight` or a small `highlight.js` call in a custom code component; use `rehype-highlight` if added, otherwise:

```tsx
import hljs from "highlight.js/lib/common";
...
const html = lang ? hljs.highlight(String(children), { language: lang }).value : ...
```

Never use `dangerouslySetInnerHTML` for untrusted Markdown except through highlight.js output with safe escaping; prefer `rehype-highlight` to avoid manual HTML.

- [ ] **Step 4: Add copy buttons per code block**

Use the DS `CopyButton`/`IconButton` with `Copy` label; keep the whole-answer Copy Markdown as a subtle icon action.

- [ ] **Step 5: Run tests/build and commit**

```powershell
bun run test -- src/chat/MarkdownBlock.test.tsx
bun run build
git add apps/web/package.json apps/web/bun.lock apps/web/src/chat
git commit -m "feat(web): style markdown and highlight code"
```

---

### Task 10: Safe Mermaid renderer

**Files:**
- Modify: `apps/web/src/chat/MermaidBlock.tsx`
- Test: `apps/web/src/chat/MermaidBlock.test.tsx`
- Modify: `apps/web/src/chat/MarkdownBlock.tsx`

**Interfaces:**
- `MermaidBlock({ source, complete }: { source: string; complete: boolean })`.
- While incomplete, show a “diagram building…” code state.
- Complete fences parse/render off-DOM; failures show a compact fallback.

- [ ] **Step 1: Write failing tests**

Mock `mermaid.parse`/`render`:
- incomplete source never calls render;
- complete valid source renders;
- failure shows fallback and no document-level error node;
- source change resets failure.

- [ ] **Step 2: Implement complete-fence rendering**

`MarkdownBlock` tracks whether the code fence is complete. In streaming content, a fenced block is complete only when a closing ``` is present. Pass `complete` to Mermaid. `MermaidBlock` calls `mermaid.parse(source)` first, then `mermaid.render` inside a detached container, and cleans up the temporary element in `finally`.

- [ ] **Step 3: Add a compact fallback**

Render a small `Panel`/`code` row with “Diagram could not be rendered”, the source, and a copy button. Never return raw Mermaid error SVGs.

- [ ] **Step 4: Run tests and commit**

```powershell
bun run test -- src/chat/MermaidBlock.test.tsx
git add apps/web/src/chat/MermaidBlock.tsx apps/web/src/chat/MermaidBlock.test.tsx apps/web/src/chat/MarkdownBlock.tsx
git commit -m "fix(web): render mermaid only when complete"
```

---

### Task 11: Message shell, history activity chips, attachments

**Files:**
- Create: `apps/web/src/chat/MessageTurn.tsx`
- Create: `apps/web/src/chat/ActivityChips.tsx`
- Create: `apps/web/src/chat/AttachmentChip.tsx`
- Create: `apps/web/src/chat/chat.module.css`
- Test: `apps/web/src/chat/MessageTurn.test.tsx`
- Test: `apps/web/src/chat/ActivityChips.test.tsx`

**Interfaces:**
- `MessageTurn({ message, agentName })` renders user/assistant shells, Markdown, attachments, activity chips.
- `ActivityChips({ activity })` renders compact chips and expandable tool rows.
- `AttachmentChip` links to the download endpoint.

- [ ] **Step 1: Write failing tests**

Assert user attachment filename renders and downloads link contains `/attachments/`; assistant activity chips show reasoning/tool counts; expanding shows tool name/status/duration.

- [ ] **Step 2: Implement components**

Use UX-1 `Panel`, `Badge`, `StatusChip`, `Icon`, `CopyButton`. Activity chips use `details` or a small controlled disclosure. Attachment chips use DS `Badge`/button styling and the API client with auth token.

- [ ] **Step 3: Run tests and commit**

```powershell
bun run test -- src/chat/MessageTurn.test.tsx src/chat/ActivityChips.test.tsx
git add apps/web/src/chat
git commit -m "feat(web): add chat message shells and activity chips"
```

---

### Task 12: Error card, cancelled state, retry

**Files:**
- Create: `apps/web/src/chat/ErrorCard.tsx`
- Create: `apps/web/src/chat/RunStatus.tsx`
- Test: `apps/web/src/chat/ErrorCard.test.tsx`
- Modify: `apps/web/src/chat/MessageTurn.tsx`

**Interfaces:**
- `ErrorCard({ error, onRetry })`.
- `RunStatus({ running, elapsedMs, onStop })` uses a spinner + “Thinking…” + Stop.
- Cancelled assistant turns show `StatusChip tone="warning">cancelled` and partial text.

- [ ] **Step 1: Write failing tests**

Assert Retry calls `onRetry`, Stop calls `onStop`, cancelled status renders, and error details appear.

- [ ] **Step 2: Implement**

Use `Spinner`, `Button`, `StatusChip`, and the design tokens. Retry button label `Retry`; Stop label `Stop`.

- [ ] **Step 3: Run tests and commit**

```powershell
bun run test -- src/chat/ErrorCard.test.tsx
git add apps/web/src/chat
git commit -m "feat(web): add run status, errors, and retry"
```

---

### Task 13: Auto-scroll and jump-to-latest

**Files:**
- Create: `apps/web/src/chat/useAutoScroll.ts`
- Test: `apps/web/src/chat/useAutoScroll.test.tsx`
- Modify: `apps/web/src/pages/SessionPage.tsx`

**Interfaces:**
- `useAutoScroll(ref, deps)` returns `{ atBottom, scrollToBottom }`.
- Auto-scroll only when the user is within 64px of the bottom.
- Show a floating `Jump to latest` button when not at bottom and new content arrives.

- [ ] **Step 1: Write failing hook test**

Simulate scroll position and content growth; assert scrollTop follows when at bottom, stays when scrolled up, and `scrollToBottom` moves to the end.

- [ ] **Step 2: Implement and integrate**

Use `useLayoutEffect` on segment/text changes; respect `prefers-reduced-motion` in `scrollTo`.

- [ ] **Step 3: Run tests and commit**

```powershell
bun run test -- src/chat/useAutoScroll.test.tsx
git add apps/web/src/chat apps/web/src/pages/SessionPage.tsx
git commit -m "feat(web): add chat auto-scroll and jump to latest"
```

---

### Task 14: Composer redesign

**Files:**
- Modify: `apps/web/src/chat/Composer.tsx`
- Create: `apps/web/src/chat/composer.module.css`
- Test: `apps/web/src/chat/Composer.test.tsx`

**Interfaces:**
- Icon-first toolbar: paperclip, mic, Ask/Agent segmented control, Send/Stop.
- Enter sends; Shift+Enter newline; empty input disables Send.
- Drag/drop attachments and styled `/`/`@` popovers.

- [ ] **Step 1: Update tests**

Assert Enter calls send, Shift+Enter does not, empty Send disabled, running shows Stop, attach input calls upload, mode switch works.

- [ ] **Step 2: Implement with DS**

Use `Textarea`, `SegmentedControl`, `IconButton` (`RiAttachment2`, `RiMicLine`/`RiMicOffLine`, `RiSendPlane2Line`, `RiStopLine`), `FileDropzone` behavior, and `Tooltip`. Preserve `data-testid="skill-menu"`/`"file-menu"` and `aria-label="Message"`.

- [ ] **Step 3: Run tests and build**

```powershell
bun run test -- src/chat/Composer.test.tsx
bun run build
git add apps/web/src/chat
git commit -m "feat(web): redesign the chat composer"
```

---

### Task 15: Fork banner and edit state

**Files:**
- Create: `apps/web/src/chat/ForkBanner.tsx`
- Test: `apps/web/src/chat/ForkBanner.test.tsx`
- Modify: `apps/web/src/pages/SessionPage.tsx`

**Interfaces:**
- Banner: “Editing from this turn — sending creates a new branch” + Cancel.
- Cancel clears edit/fork mode and restores prior input state.

- [ ] **Step 1: Write failing test**

Click Edit on a historical user turn, assert banner appears, Cancel hides it and clears fork mode.

- [ ] **Step 2: Implement and integrate**

Use `StatusChip`/`Panel` styling and `IconButton`. Sending with fork mode passes `fork_from_turn_id` as before; after send, clear banner.

- [ ] **Step 3: Run tests and commit**

```powershell
bun run test -- src/chat/ForkBanner.test.tsx
git add apps/web/src/chat apps/web/src/pages/SessionPage.tsx
git commit -m "feat(web): add visible edit/fork mode"
```

---

### Task 16: SessionPage integration

**Files:**
- Modify: `apps/web/src/pages/SessionPage.tsx`
- Modify: `apps/web/src/chat/useChat.ts`
- Test: `apps/web/src/pages/SessionPage.test.tsx`

**Interfaces:**
- Renders history via `MessageTurn`, live via ordered segments, sticky composer, run status, error/retry, attachments, fork banner.
- Retry calls `chat.send` with `retryTurnId`.

- [ ] **Step 1: Update tests**

Cover: history activity chips, live segment order, Stop calls cancel, Retry sends with `retryTurnId`, error card appears, attachments render.

- [ ] **Step 2: Rewrite the page shell**

Use `PageContainer`/`Panel`/design-system components; remove all Bulma class names from this file. Keep `data-testid="session-agent"`, About modal, PlanPanel, app panel.

- [ ] **Step 3: Run tests/build**

```powershell
bun run test -- src/pages/SessionPage.test.tsx src/pages/SessionPage.avatar.test.tsx
bun run build
git add apps/web/src/pages/SessionPage.tsx apps/web/src/chat/useChat.ts apps/web/src/pages/SessionPage.test.tsx
git commit -m "feat(web): rebuild the session surface"
```

---

### Task 17: MCP app split view

**Files:**
- Modify: `apps/web/src/chat/AppPanel.tsx`
- Create: `apps/web/src/chat/ChatSplit.tsx`
- Create: `apps/web/src/chat/chat-split.module.css`
- Test: `apps/web/src/chat/ChatSplit.test.tsx`

**Interfaces:**
- Desktop: resizable chat/app split with keyboard-accessible divider.
- Mobile: app panel as a full-screen sheet.

- [ ] **Step 1: Write failing tests**

Assert chat and app panes render when tabs exist, divider drag changes width, and mobile sheet opens/closes.

- [ ] **Step 2: Implement**

Use CSS grid, pointer events for the divider, `useMediaQuery` for mobile, `Drawer`/sheet for small screens. Keep `data-testid="app-panel"` and tab labels `App N`.

- [ ] **Step 3: Run tests and commit**

```powershell
bun run test -- src/chat/ChatSplit.test.tsx
git add apps/web/src/chat
git commit -m "feat(web): add resizable MCP app split view"
```

---

### Task 18: Remove Bulma and legacy chat styles

**Files:**
- Delete: `apps/web/src/design-system/styles/legacy-chat.css`
- Delete: `apps/web/src/design-system/styles/legacy.css`
- Modify: `apps/web/src/main.tsx`
- Modify: `apps/web/src/design-system/styles/no-bulma.test.ts`
- Modify: `apps/web/package.json`

**Interfaces:**
- No Bulma import or dependency.
- No legacy chat classes remain.

- [ ] **Step 1: Update the no-Bulma guard**

Remove the chat allowlist and assert no banned class names anywhere in `src`; remove `legacy.css`/`legacy-chat.css` references.

- [ ] **Step 2: Remove import and dependency**

Remove `./design-system/styles/legacy.css` and `legacy-chat.css` imports from `main.tsx`/`SessionPage.tsx`; run:

```powershell
cd apps/web
bun remove bulma
```

- [ ] **Step 3: Run tests/build/storybook**

```powershell
bun run test
bun run build
bun run build-storybook
git add apps/web
git commit -m "refactor(web): remove Bulma from the chat surface"
```

---

### Task 19: E2E updates and deterministic chat scenarios

**Files:**
- Modify: `apps/web/e2e/chat.spec.ts`
- Modify: `apps/web/e2e/mcp-apps.spec.ts`
- Modify: `apps/web/e2e/avatars.spec.ts`
- Create: `apps/web/e2e/chat-ux2.spec.ts`
- Modify: `packages/agentbox-providers/src/agentbox_providers/resolver.py` if a deterministic tool-call provider is needed.

**Interfaces:**
- E2E covers live tool cards, cancel/stop, error/retry, attachment history/download, Mermaid success/failure, and MCP split.

- [ ] **Step 1: Add a deterministic tool-call scenario**

Use the existing `test_tool` provider (or add `test_chat`) to produce a tool call followed by text. Assert the tool card appears before the assistant Markdown and the final text is visible.

- [ ] **Step 2: Add cancel and retry scenarios**

- Start a slow deterministic run; click Stop; assert partial text/status cancelled/Retry.
- Force a provider error; assert per-turn error card; click Retry; assert success.
- Use a unique model per test to avoid name collisions.

- [ ] **Step 3: Add attachment/Markdown/Mermaid scenarios**

Upload a file, send, reload, assert attachment chip and download response; send a Markdown/Mermaid answer and assert styled table/code and diagram fallback/success.

- [ ] **Step 4: Run E2E and commit**

```powershell
cd apps/web
bun run e2e
git add apps/web/e2e
git commit -m "test(web): cover chat UX-2 flows"
```

---

### Task 20: Storybook chat stories and screenshot pack

**Files:**
- Modify: `apps/web/.storybook/main.ts` (include `../src/chat/**/*.stories.@(ts|tsx)`)
- Create: `apps/web/src/chat/chat.stories.tsx`
- Create: `apps/web/scripts/screenshots-ux2.mjs`
- Create: `docs/reviews/2026-11-21-ux-2/README.md`
- Create: `docs/reviews/2026-11-21-ux-2/*.png`

**Interfaces:**
- Stories for Markdown, Mermaid success/failure, live segments, activity chips, error card, running status, composer, fork banner, attachment chips, split view.
- Screenshot script opens Storybook story URLs and saves deterministic screenshots.

- [ ] **Step 1: Add chat stories**

Create stories with fixed props for each state, light/dark via the existing Storybook toolbar. Include `ActivityChips` collapsed/expanded, `MessageTurn` with attachments, `ErrorCard`, `RunStatus`, `Composer`, `MermaidBlock` success/failure, and `ChatSplit`.

- [ ] **Step 2: Write the screenshot script**

Use Playwright's Node API to open `http://localhost:6006/iframe.html?id=chat-...&globals=theme:dark` and save screenshots into `docs/reviews/2026-11-21-ux-2/`. Include desktop and mobile (`viewport 390x844`).

- [ ] **Step 3: Add live app screenshots**

Use Playwright against the running app with the deterministic test provider for running/stopped/error states; save to the same folder.

- [ ] **Step 4: Write the README**

Embed each screenshot with a one-line caption and group by state. Keep it short so it can be scanned quickly.

- [ ] **Step 5: Run screenshot script and commit**

```powershell
cd apps/web
bun run build-storybook
# Terminal 1 from apps/web:
bun run storybook -- --ci
# Terminal 2 from apps/web, once Storybook is listening on 6006:
bun run scripts/screenshots-ux2.mjs
git add apps/web/.storybook apps/web/src/chat/chat.stories.tsx apps/web/scripts/screenshots-ux2.mjs docs/reviews/2026-11-21-ux-2
git commit -m "docs(ux): add UX-2 screenshot pack"
```

---

### Task 21: Final cleanup, roadmap, and verification

**Files:**
- Modify: `docs/ROADMAP.md`
- Modify: `docs/superpowers/plans/2026-11-21-ux-2-chat-surface.md` (mark progress)
- Optional: `apps/web/e2e/visual-shell.spec.ts` add chat smoke if not covered.

- [ ] **Step 1: Update roadmap**

Set `UX-2` to `DONE`, add sub-project history row 31 for UX-2, and update the chat requirement row (Markdown/reasoning/tool/stop/errors/attachments).

- [ ] **Step 2: Run all checks**

```powershell
cd apps/web
bun run test
bun run build
bun run build-storybook
bun run e2e
cd ../..
uv run pytest packages/agentbox-api -q
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-providers -q
uv run ruff check packages
uv run ty check packages
```

- [ ] **Step 3: Confirm the screenshot pack exists**

Verify `docs/reviews/2026-11-21-ux-2/README.md` embeds every required screenshot and all files exist.

- [ ] **Step 4: Commit**

```powershell
git add docs/ROADMAP.md docs/superpowers/plans/2026-11-21-ux-2-chat-surface.md
git commit -m "feat(web): complete UX-2 chat surface"
```

---

## Plan self-review

- **Spec coverage:** Task 1–6 backend (metadata, activity, retry, cancel, errors, download); Tasks 7–18 frontend (segments, useChat, Markdown, Mermaid, message shells, errors/retry, auto-scroll, composer, fork, SessionPage, split, Bulma removal); Task 19 E2E; Task 20 screenshots; Task 21 roadmap/verification.
- **Placeholder scan:** no TBD/TODO steps; every task has files, tests/verification, and implementation snippets or exact extraction instructions.
- **Type consistency:** `Turn.activity`/`attachments` are used consistently; `retry_turn_id`, `record_user_turn`, `RunActivityCollector`, `Segment`, `applyAgUiEvent`, `chat.send({retryTurnId})`, and `RunStatus` names are consistent across tasks.
- **Ordering:** reducer tests explicitly cover interleaving; useChat integration preserves event order; history uses summary chips because full ordering is not persisted by design.

