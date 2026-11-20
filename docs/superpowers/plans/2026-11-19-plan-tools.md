# Session Plan Tools (TODO-*) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add granular session-scoped TODO tools, a normalized plan table, a plan API, and a collapsible plan panel above the chat.

**Architecture:** `PlanItem` + `plan_tools.py` in the API, wired into `prepare_agent` as always-on native tools; a sessions endpoint feeds a `PlanPanel` in `SessionPage`.

**Tech Stack:** Python 3.12, SQLModel/Alembic, pydantic-ai `ModelRetry`, FastAPI, React/Mantine, react-query, Vitest.

## Global Constraints

- Tools: `todo_add`, `todo_update`, `todo_complete`, `todo_remove`, `todo_reorder`, `todo_list`, `todo_clear`.
- Always available (no `write` flag); added to the spec bindings when `session_id` is present.
- Plan is per session; normalized `planitem` table; no priorities or history.
- Invalid operations raise `pydantic_ai.ModelRetry`.
- Content trimmed, 1–500 chars; statuses `pending|in_progress|completed`.
- `delete_session_data` removes plan items.
- Regenerate `apps/web/openapi.json` + `schema.d.ts` after the API change.
- Run `ruff`/`ty` and relevant tests before each commit.

---

### Task 1: PlanItem model, migration, tools, and tool tests

**Files:**
- Modify: `packages/agentbox-models/src/agentbox_models/tables/core.py`
- Create: `packages/agentbox-models/alembic/versions/e1f2a3b4c5d6_plan_items.py`
- Create: `packages/agentbox-api/src/agentbox_api/plan_tools.py`
- Test: `packages/agentbox-api/tests/test_plan_tools.py`

**Interfaces:**
- Produces: `PlanItem`, `PLAN_TOOL_NAMES`, `make_plan_tools(factory, session_id) -> dict[str, Callable]`.

- [ ] **Step 1: Add the table**

Append to `tables/core.py`:

```python
class PlanItem(SQLModel, table=True):
    id: str = Field(primary_key=True)
    session_id: str = Field(foreign_key="sessionrow.id", index=True)
    position: int = 0
    content: str
    status: str = "pending"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
```

- [ ] **Step 2: Migration**

`e1f2a3b4c5d6_plan_items.py` (down_revision `c4f8e2a1b9d3`):

```python
def upgrade() -> None:
    op.create_table(
        "planitem",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessionrow.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_planitem_session_id", "planitem", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_planitem_session_id", table_name="planitem")
    op.drop_table("planitem")
```

- [ ] **Step 3: Write failing tool tests**

```python
import pytest
from pydantic_ai import ModelRetry
from sqlmodel import select

from agentbox_api.plan_tools import make_plan_tools
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import PlanItem, SessionRow


async def _tools():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    return engine, factory, make_plan_tools(factory, "s1")


async def _items(factory):
    async with factory() as s:
        return (await s.execute(select(PlanItem).order_by(PlanItem.position))).scalars().all()


async def test_add_list_update_complete_and_clear():
    engine, factory, tools = await _tools()
    try:
        await tools["todo_add"]("first")
        await tools["todo_add"]("second")
        items = await _items(factory)
        assert [item.position for item in items] == [0, 1]
        assert "first" in await tools["todo_list"]()
        await tools["todo_update"](items[0].id, content="renamed", status="in_progress")
        assert (await _items(factory))[0].content == "renamed"
        await tools["todo_complete"](items[1].id)
        assert (await _items(factory))[1].status == "completed"
        await tools["todo_clear"]()
        assert await _items(factory) == []
        assert await tools["todo_list"]() == "TODO list is empty."
    finally:
        await engine.dispose()


async def test_remove_compacts_and_reorder_validates():
    engine, factory, tools = await _tools()
    try:
        for text in ("a", "b", "c"):
            await tools["todo_add"](text)
        items = await _items(factory)
        await tools["todo_remove"](items[1].id)
        remaining = await _items(factory)
        assert [item.position for item in remaining] == [0, 1]
        await tools["todo_reorder"]([remaining[1].id, remaining[0].id])
        assert [item.content for item in await _items(factory)] == ["c", "a"]
        with pytest.raises(ModelRetry):
            await tools["todo_reorder"]([remaining[0].id])
    finally:
        await engine.dispose()


async def test_invalid_operations_raise_model_retry():
    engine, factory, tools = await _tools()
    try:
        with pytest.raises(ModelRetry):
            await tools["todo_add"]("   ")
        with pytest.raises(ModelRetry):
            await tools["todo_update"]("missing", content="x")
        await tools["todo_add"]("x")
        item = (await _items(factory))[0]
        with pytest.raises(ModelRetry):
            await tools["todo_update"](item.id, status="nope")
    finally:
        await engine.dispose()


async def test_delete_session_data_removes_plan():
    from agentbox_api.runtime import delete_session_data

    engine, factory, tools = await _tools()
    try:
        async with factory() as s:
            s.add(SessionRow(id="s1", project_id="p", agent_id="a"))
            await s.commit()
        await tools["todo_add"]("x")
        await delete_session_data(factory, "s1")
        assert await _items(factory) == []
    finally:
        await engine.dispose()
```

- [ ] **Step 4: Implement tools**

Create `plan_tools.py` with the full implementation from the spec:

```python
PLAN_TOOL_NAMES = (
    "todo_add", "todo_update", "todo_complete",
    "todo_remove", "todo_reorder", "todo_list", "todo_clear",
)
STATUSES = {"pending", "in_progress", "completed"}
MAX_CONTENT = 500
MARKS = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}


def make_plan_tools(factory, session_id):
    async def _load(s):
        return (await s.execute(
            select(PlanItem)
            .where(PlanItem.session_id == session_id)
            .order_by(PlanItem.position)
        )).scalars().all()

    def _content(value):
        text = (value or "").strip()
        if not text:
            raise ModelRetry("TODO content must not be empty.")
        if len(text) > MAX_CONTENT:
            raise ModelRetry(f"TODO content must be at most {MAX_CONTENT} characters.")
        return text

    async def _new_id(s):
        while True:
            candidate = uuid.uuid4().hex[:8]
            if await s.get(PlanItem, candidate) is None:
                return candidate

    async def _get(s, item_id):
        item = await s.get(PlanItem, item_id)
        if item is None or item.session_id != session_id:
            raise ModelRetry(f"Unknown TODO id: {item_id}")
        return item

    async def todo_add(content: str) -> str:
        text = _content(content)
        async with factory() as s:
            items = await _load(s)
            position = max((item.position for item in items), default=-1) + 1
            item = PlanItem(id=await _new_id(s), session_id=session_id, position=position, content=text)
            s.add(item)
            await s.commit()
        return f"Added {item.id}: {text}"

    async def todo_update(item_id: str, content: str | None = None, status: str | None = None) -> str:
        if content is None and status is None:
            raise ModelRetry("Provide content and/or status.")
        if status is not None and status not in STATUSES:
            raise ModelRetry(f"Invalid status: {status}")
        async with factory() as s:
            item = await _get(s, item_id)
            if content is not None:
                item.content = _content(content)
            if status is not None:
                item.status = status
            item.updated_at = utcnow()
            s.add(item)
            await s.commit()
        return f"Updated {item_id}"

    async def todo_complete(item_id: str) -> str:
        async with factory() as s:
            item = await _get(s, item_id)
            item.status = "completed"
            item.updated_at = utcnow()
            s.add(item)
            await s.commit()
        return f"Completed {item_id}"

    async def todo_remove(item_id: str) -> str:
        async with factory() as s:
            item = await _get(s, item_id)
            await s.delete(item)
            await s.flush()
            remaining = await _load(s)
            for position, entry in enumerate(remaining):
                entry.position = position
                s.add(entry)
            await s.commit()
        return f"Removed {item_id}"

    async def todo_reorder(item_ids: list[str]) -> str:
        if len(set(item_ids)) != len(item_ids):
            raise ModelRetry("TODO reorder list contains duplicates.")
        async with factory() as s:
            items = await _load(s)
            if {item.id for item in items} != set(item_ids):
                raise ModelRetry("TODO reorder must include every current id exactly once.")
            by_id = {item.id: item for item in items}
            for position, item_id in enumerate(item_ids):
                entry = by_id[item_id]
                entry.position = position
                s.add(entry)
            await s.commit()
        return f"Reordered {len(item_ids)} items"

    async def todo_list() -> str:
        async with factory() as s:
            items = await _load(s)
        if not items:
            return "TODO list is empty."
        lines = [f"TODO list ({len(items)} items):"]
        lines.extend(
            f"{MARKS.get(item.status, '[ ]')} #{item.position} {item.id} {item.content}"
            for item in items
        )
        return "\n".join(lines)

    async def todo_clear() -> str:
        async with factory() as s:
            for item in await _load(s):
                await s.delete(item)
            await s.commit()
        return "TODO list cleared"

    return {name: value for name, value in locals().items() if name in PLAN_TOOL_NAMES}
```

- [ ] **Step 5: Wire cleanup**

In `agentbox_api/runtime.py`, import `PlanItem` and delete plan rows in `delete_session_data`:

```python
        for item in (
            await s.execute(select(PlanItem).where(PlanItem.session_id == session_id))
        ).scalars().all():
            await s.delete(item)
```

- [ ] **Step 6: Run and commit**

```bash
uv run pytest packages/agentbox-api/tests/test_plan_tools.py -q
uv run alembic -c packages/agentbox-models/alembic.ini upgrade head  # on a scratch DB if configured
git add packages/agentbox-models/src/agentbox_models/tables/core.py packages/agentbox-models/alembic/versions/e1f2a3b4c5d6_plan_items.py packages/agentbox-api/src/agentbox_api/plan_tools.py packages/agentbox-api/src/agentbox_api/runtime.py packages/agentbox-api/tests/test_plan_tools.py
git commit -m "feat(api): session plan model and TODO tools"
```

---

### Task 2: Plan API endpoint

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`
- Test: `packages/agentbox-api/tests/test_session_plan.py`

- [ ] **Step 1: Endpoint**

Add to `sessions.py` (needs `PlanItem` import and `PlanRead` schema):

```python
class PlanItemRead(BaseModel):
    id: str
    position: int
    content: str
    status: str


class PlanRead(BaseModel):
    items: list[PlanItemRead]


@router.get("/{sid}/plan", response_model=PlanRead)
async def session_plan(
    sid: str, request: Request, _=Depends(require_permission("sessions:read"))
):
    factory = request.app.state.session_factory
    async with factory() as s:
        if await s.get(SessionRow, sid) is None:
            raise HTTPException(status_code=404, detail="Session not found")
        items = (await s.execute(
            select(PlanItem)
            .where(PlanItem.session_id == sid)
            .order_by(PlanItem.position)
        )).scalars().all()
    return PlanRead(
        items=[
            PlanItemRead(
                id=item.id, position=item.position, content=item.content, status=item.status
            )
            for item in items
        ]
    )
```

- [ ] **Step 2: Test**

Create `test_session_plan.py` (setup like `test_session_lsp.py`), then insert two `PlanItem` rows and assert the endpoint order and 404.

- [ ] **Step 3: Run and commit**

```bash
uv run pytest packages/agentbox-api/tests/test_session_plan.py -q
git add packages/agentbox-api/src/agentbox_api/routers/sessions.py packages/agentbox-api/tests/test_session_plan.py
git commit -m "feat(api): session plan endpoint"
```

---

### Task 3: Wire tools into agents

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/skills.py`
- Test: `packages/agentbox-api/tests/test_plan_wiring.py`

- [ ] **Step 1: Wiring**

In `prepare_agent`:

```python
from agentbox_api.plan_tools import PLAN_TOOL_NAMES, make_plan_tools

    extra_tools = {"activate_skill": make_activate_tool(skills)} if skills else {}
    if session_id:
        extra_tools.update(make_plan_tools(factory, session_id))
    ...
    spec = augment_spec(spec, skills)
    if session_id:
        existing = {
            binding.name
            for binding in spec.tool_bindings
            if isinstance(binding, NativeToolBinding)
        }
        additions = [
            NativeToolBinding(name=name)
            for name in PLAN_TOOL_NAMES
            if name not in existing
        ]
        if additions:
            spec = spec.model_copy(
                update={"tool_bindings": [*spec.tool_bindings, *additions]}
            )
    ...
    registry = build_registry(
        ...,
        extra_tools=extra_tools or None,
        ...
    )
```

- [ ] **Step 2: Test**

Build a DB with provider/model/agent (no skills), call
`prepare_agent(factory, "bot", str(tmp), str(tmp / "skills"), session_id="s1")`,
then assert:

```python
from agentbox_api.plan_tools import PLAN_TOOL_NAMES
from agentbox_harness.spec import Mode

tools = prepared.registry.select_tools(Mode(name="ask", flags={"write": False}))
names = {tool.__name__ for tool in tools}
assert set(PLAN_TOOL_NAMES) <= names
assert await next(t for t in tools if t.__name__ == "todo_list")() == "TODO list is empty."
```

- [ ] **Step 3: Run and commit**

```bash
uv run pytest packages/agentbox-api/tests/test_plan_wiring.py packages/agentbox-api/tests/test_prompt_rendering.py -q
git add packages/agentbox-api/src/agentbox_api/skills.py packages/agentbox-api/tests/test_plan_wiring.py
git commit -m "feat(api): expose TODO tools to every agent session"
```

---

### Task 4: Web client, PlanPanel, SessionPage

**Files:**
- Regenerate: `apps/web/openapi.json`, `apps/web/src/api/schema.d.ts`
- Modify: `apps/web/src/api/endpoints.ts`, `apps/web/src/api/queries.ts`
- Create: `apps/web/src/chat/PlanPanel.tsx`
- Modify: `apps/web/src/pages/SessionPage.tsx`
- Test: `apps/web/src/chat/PlanPanel.test.tsx`; update `SessionPage.avatar.test.tsx` mock.

- [ ] **Step 1: Regenerate**

```bash
uv run python apps/web/scripts/gen-openapi.py
cd apps/web && bun run codegen
```

- [ ] **Step 2: Endpoint + query**

```ts
export type PlanItem = {
  id: string;
  position: number;
  content: string;
  status: string;
};
export type SessionPlan = { items: PlanItem[] };

export async function fetchSessionPlan(sid: string): Promise<SessionPlan> {
  const { data, error } = await api.GET("/sessions/{sid}/plan", {
    params: { path: { sid } },
  });
  if (error) throw new Error("Failed to load session plan");
  return data as SessionPlan;
}
```

```ts
export function useSessionPlan(sessionId: string, running = false) {
  return useQuery({
    queryKey: ["session-plan", sessionId],
    queryFn: () => fetchSessionPlan(sessionId),
    enabled: !!sessionId,
    refetchInterval: running ? 2000 : false,
  });
}
```

- [ ] **Step 3: PlanPanel**

```tsx
import { Badge, Button } from "@mantine/core";
import { useState } from "react";

import type { PlanItem } from "../api/endpoints";

const COLORS: Record<string, string> = {
  pending: "gray",
  in_progress: "blue",
  completed: "green",
};

export function PlanPanel({ items }: { items: PlanItem[] }) {
  const [open, setOpen] = useState(true);
  if (items.length === 0) return null;
  return (
    <div className="box" data-testid="plan-panel" style={{ marginBottom: "0.75rem" }}>
      <div className="is-flex is-justify-content-space-between is-align-items-center">
        <strong>Plan ({items.length})</strong>
        <Button size="compact-xs" variant="subtle" onClick={() => setOpen((v) => !v)}>
          {open ? "Hide" : "Show"}
        </Button>
      </div>
      {open && (
        <ul>
          {items.map((item) => (
            <li key={item.id}>
              <Badge color={COLORS[item.status] ?? "gray"} mr={6}>
                {item.status}
              </Badge>
              {item.content}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 4: SessionPage**

```tsx
import { useMessages, useSession, useSessionLsp, useSessionPlan } from "../api/queries";
import { PlanPanel } from "../chat/PlanPanel";
...
  const { data: plan } = useSessionPlan(id, chat.running);
...
        <h1 className="title">Session</h1>
        <PlanPanel items={plan?.items ?? []} />
        <div className="session-messages">
...
    await chat.send(...);
    await qc.refetchQueries({ queryKey: ["messages", id] });
    await qc.invalidateQueries({ queryKey: ["session-plan", id] });
    chat.reset();
```

- [ ] **Step 5: Tests**

`PlanPanel.test.tsx`: render items/statuses, click Hide, empty returns null.
Add `useSessionPlan: () => ({ data: { items: [] } })` to the
`SessionPage.avatar.test.tsx` query mock.

- [ ] **Step 6: Run and commit**

```bash
cd apps/web && bun run test && bun run build
git add apps/web/openapi.json apps/web/src/api/schema.d.ts apps/web/src/api/endpoints.ts apps/web/src/api/queries.ts apps/web/src/chat/PlanPanel.tsx apps/web/src/chat/PlanPanel.test.tsx apps/web/src/pages/SessionPage.tsx apps/web/src/pages/SessionPage.avatar.test.tsx
git commit -m "feat(web): session plan panel"
```

---

### Task 5: Roadmap and full verification

**Files:**
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Update the roadmap**

Remove the D14 row and add:

```markdown
| 25 | Session plan tools (TODO-*) | `specs/2026-11-19-plan-tools-design.md` | `plans/2026-11-19-plan-tools.md` |
```

- [ ] **Step 2: Verify**

```bash
uv run ruff check --fix packages
uv run ty check packages
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-api -q
cd apps/web && bun run test && bun run build
```

- [ ] **Step 3: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs(roadmap): session plan tools complete"
```
