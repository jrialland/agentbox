# Sub-agent Sessions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persisted background child sessions with a unified start/wait tool, status/output monitoring, cancellation, write-flag gating, and bounded depth/concurrency.

**Architecture:** `SessionRow` gains parent/status/depth fields. A harness `SubSessionRunner` protocol feeds four agent tools; the API implements it with an in-process task registry, `prepare_agent`-prepared child agents, and persisted child turns. Parent deletion and backend lifecycle clean up children.

**Tech Stack:** Python 3.12, pydantic-ai, SQLModel/Alembic, FastAPI, asyncio.

## Global Constraints

- Tools: `start_sub_session(agent, task, wait=False)`, `list_sub_sessions`, `get_sub_session`, `cancel_sub_session`.
- Only `spec.sub_agent_ids` may be started.
- Tools require the parent `write` flag; Ask mode excludes them.
- Background by default; `wait=True` returns the child output.
- Max 5 running children per parent; max depth 3.
- Child sessions are persisted, hidden from `GET /sessions`, and use the parent's project context.
- Child mode is `agent`.
- `get_sub_session` returns status plus the latest assistant output or error.
- Run `ruff`/`ty` and relevant tests before each commit.
- Implementation note: the runner caches completed output in
  `SessionRow.sub_session_output` so status/output updates are atomic, keeps
  active tasks until `get`/`list` observes a terminal status (avoiding a
  completion race), and runner tests use a file-backed SQLite database so the
  background child and polling reader do not share a single in-memory
  connection.

---

### Task 1: Session fields, migration, and hidden child sessions

**Files:**
- Modify: `packages/agentbox-models/src/agentbox_models/tables/core.py`
- Create: `packages/agentbox-models/alembic/versions/c3d4e5f6a7b8_sub_sessions.py`
- Create: `packages/agentbox-models/tests/test_sub_session_fields.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`
- Create: `packages/agentbox-api/tests/test_sub_sessions_list.py`

**Interfaces:**
- Produces: `SessionRow.parent_session_id`, `sub_session_status`, `sub_session_error`, `sub_session_depth`; top-level-only `GET /sessions`.

- [ ] **Step 1: Write the failing model test**

Create `packages/agentbox-models/tests/test_sub_session_fields.py`:

```python
from sqlmodel import select

from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import SessionRow


async def test_sub_session_fields_roundtrip():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    try:
        async with factory() as s:
            s.add(
                SessionRow(
                    id="parent",
                    project_id="p",
                    agent_id="a",
                )
            )
            s.add(
                SessionRow(
                    id="child",
                    project_id="p",
                    agent_id="b",
                    parent_session_id="parent",
                    sub_session_status="running",
                    sub_session_error=None,
                    sub_session_depth=1,
                )
            )
            await s.commit()
        async with factory() as s:
            child = (
                await s.execute(select(SessionRow).where(SessionRow.id == "child"))
            ).scalars().first()
        assert child is not None
        assert child.parent_session_id == "parent"
        assert child.sub_session_status == "running"
        assert child.sub_session_depth == 1
    finally:
        await engine.dispose()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest packages/agentbox-models/tests/test_sub_session_fields.py -q`

Expected: FAIL because the fields are missing.

- [ ] **Step 3: Add the fields and migration**

Add to `SessionRow`:

```python
    parent_session_id: str | None = Field(
        default=None, foreign_key="sessionrow.id", index=True
    )
    sub_session_status: str | None = None
    sub_session_error: str | None = None
    sub_session_output: str | None = None
    sub_session_depth: int = 0
```

Create `packages/agentbox-models/alembic/versions/c3d4e5f6a7b8_sub_sessions.py`:

```python
"""sub-agent sessions

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-20 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessionrow",
        sa.Column(
            "parent_session_id",
            sa.String(),
            sa.ForeignKey("sessionrow.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_sessionrow_parent_session_id", "sessionrow", ["parent_session_id"]
    )
    op.add_column("sessionrow", sa.Column("sub_session_status", sa.String(), nullable=True))
    op.add_column("sessionrow", sa.Column("sub_session_error", sa.String(), nullable=True))
    op.add_column("sessionrow", sa.Column("sub_session_output", sa.String(), nullable=True))
    op.add_column(
        "sessionrow",
        sa.Column("sub_session_depth", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("sessionrow", "sub_session_depth")
    op.drop_column("sessionrow", "sub_session_output")
    op.drop_column("sessionrow", "sub_session_error")
    op.drop_column("sessionrow", "sub_session_status")
    op.drop_index("ix_sessionrow_parent_session_id", table_name="sessionrow")
    op.drop_column("sessionrow", "parent_session_id")
```

- [ ] **Step 4: Run the model test**

Run: `uv run pytest packages/agentbox-models/tests/test_sub_session_fields.py -q`

Expected: PASS.

- [ ] **Step 5: Write the failing sessions-list test**

Create `packages/agentbox-api/tests/test_sub_sessions_list.py`:

```python
import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import (
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)
from agentbox_models.tables.core import SessionRow


async def test_session_list_hides_children():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r1", name="role"))
        s.add(Permission(id="perm", name="sessions:read"))
        s.add(RolePermissionLink(role_id="r1", permission_id="perm"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(SessionRow(id="parent", project_id="p", agent_id="a"))
        s.add(
            SessionRow(
                id="child",
                project_id="p",
                agent_id="b",
                parent_session_id="parent",
                sub_session_status="completed",
                sub_session_depth=1,
            )
        )
        await s.commit()

    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    try:
        login = await client.post(
            "/auth/login", json={"username": "alice", "password": "pw"}
        )
        response = await client.get(
            "/sessions",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert response.status_code == 200
        assert [row["id"] for row in response.json()] == ["parent"]
    finally:
        await client.aclose()
        await engine.dispose()
```

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run pytest packages/agentbox-api/tests/test_sub_sessions_list.py -q`

Expected: FAIL because both sessions are returned.

- [ ] **Step 7: Filter top-level sessions**

In `routers/sessions.py`, replace the `list_sessions` body with:

```python
    factory = request.app.state.session_factory
    async with factory() as s:
        rows = (
            await s.execute(
                select(SessionRow).where(SessionRow.parent_session_id.is_(None))
            )
        ).scalars().all()
    return list(rows)
```

- [ ] **Step 8: Regenerate API artifacts and commit**

```bash
uv run python apps/web/scripts/gen-openapi.py
cd apps/web && bun run codegen
cd ../..
uv run pytest packages/agentbox-models/tests/test_sub_session_fields.py -q
uv run pytest packages/agentbox-api/tests/test_sub_sessions_list.py -q
uv run ruff check --fix packages
uv run ty check packages
git add packages/agentbox-models/src/agentbox_models/tables/core.py packages/agentbox-models/alembic/versions/c3d4e5f6a7b8_sub_sessions.py packages/agentbox-models/tests/test_sub_session_fields.py packages/agentbox-api/src/agentbox_api/routers/sessions.py packages/agentbox-api/tests/test_sub_sessions_list.py apps/web/openapi.json apps/web/src/api/schema.d.ts
git commit -m "feat(api): sub-session storage and hidden sessions"
```

---

### Task 2: Harness sub-session protocol, tools, and gating

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/subagents.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/agent_factory.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/harness.py`
- Create: `packages/agentbox-harness/tests/test_sub_session_tools.py`

**Interfaces:**
- Produces: `SubSessionRunner`, `make_sub_session_tools`, `build_sub_session_tools`, `Harness(sub_session_runner=...)`.

- [ ] **Step 1: Write the failing tool tests**

Create `packages/agentbox-harness/tests/test_sub_session_tools.py`:

```python
from pydantic_ai.models.test import TestModel

from agentbox_harness.agent_factory import build_sub_session_tools
from agentbox_harness.spec import AgentSpec, Mode, ModelBinding
from agentbox_harness.subagents import make_sub_session_tools


def _spec(name="parent", subs=None) -> AgentSpec:
    return AgentSpec(
        name=name,
        description="d",
        instructions="i",
        tool_bindings=[],
        sub_agent_ids=subs or [],
        model_binding=ModelBinding(model="test", provider="test"),
    )


class FakeRunner:
    def __init__(self):
        self.calls = []

    async def start(self, parent_session_id, parent_spec, agent_name, task, wait):
        self.calls.append(("start", parent_session_id, agent_name, task, wait))
        return f"started {agent_name}"

    async def list(self, parent_session_id):
        self.calls.append(("list", parent_session_id))
        return "no children"

    async def get(self, parent_session_id, sub_session_id, max_chars):
        self.calls.append(("get", parent_session_id, sub_session_id, max_chars))
        return "child"

    async def cancel(self, parent_session_id, sub_session_id):
        self.calls.append(("cancel", parent_session_id, sub_session_id))
        return "cancelled"


async def test_tools_validate_and_delegate():
    runner = FakeRunner()
    tools = make_sub_session_tools(runner, "parent-1", _spec(subs=["sub"]))
    assert await tools["start_sub_session"]("sub", "do it") == "started sub"
    assert runner.calls[-1] == ("start", "parent-1", "sub", "do it", False)
    assert "unknown agent" in await tools["start_sub_session"]("other", "do it")
    assert "must not be empty" in await tools["start_sub_session"]("sub", "  ")
    assert await tools["list_sub_sessions"]() == "no children"
    assert await tools["get_sub_session"]("child-1") == "child"
    assert await tools["cancel_sub_session"]("child-1") == "cancelled"


def test_tools_are_gated_by_subagents_and_write_mode():
    runner = FakeRunner()
    agent_mode = Mode(name="agent", flags={"write": True})
    ask_mode = Mode(name="ask", flags={"write": False})
    assert build_sub_session_tools(_spec(subs=["sub"]), agent_mode, runner, "s1")
    assert build_sub_session_tools(_spec(subs=["sub"]), ask_mode, runner, "s1") == []
    assert build_sub_session_tools(_spec(subs=[]), agent_mode, runner, "s1") == []
    assert build_sub_session_tools(_spec(subs=["sub"]), agent_mode, None, "s1") == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_sub_session_tools.py -q`

Expected: FAIL because the protocol/tools are missing.

- [ ] **Step 3: Add the protocol and tools**

In `subagents.py`, add:

```python
from typing import Protocol

from agentbox_harness.spec import AgentSpec, Mode


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

    async def cancel(
        self, parent_session_id: str, sub_session_id: str
    ) -> str: ...


def make_sub_session_tools(
    runner: SubSessionRunner,
    parent_session_id: str,
    parent_spec: AgentSpec,
) -> dict[str, Callable]:
    allowed = set(parent_spec.sub_agent_ids)

    async def start_sub_session(
        agent: str, task: str, wait: bool = False
    ) -> str:
        text = (task or "").strip()
        if not text:
            return "Sub-session failed: task must not be empty."
        if agent not in allowed:
            names = ", ".join(sorted(allowed)) or "(none)"
            return f"Sub-session failed: unknown agent {agent}. Available: {names}"
        return await runner.start(
            parent_session_id, parent_spec, agent, text, wait
        )

    async def list_sub_sessions() -> str:
        return await runner.list(parent_session_id)

    async def get_sub_session(
        sub_session_id: str, max_chars: int = 4000
    ) -> str:
        return await runner.get(parent_session_id, sub_session_id, max_chars)

    async def cancel_sub_session(sub_session_id: str) -> str:
        return await runner.cancel(parent_session_id, sub_session_id)

    return {
        "start_sub_session": start_sub_session,
        "list_sub_sessions": list_sub_sessions,
        "get_sub_session": get_sub_session,
        "cancel_sub_session": cancel_sub_session,
    }


def build_sub_session_tools(
    spec: AgentSpec,
    mode: Mode,
    runner: SubSessionRunner | None,
    session_id: str | None,
) -> list[Callable]:
    if runner is None or not spec.sub_agent_ids or not session_id:
        return []
    if not mode.allows("write"):
        return []
    return list(
        make_sub_session_tools(runner, session_id, spec).values()
    )
```

- [ ] **Step 4: Wire tools into `build_agent`**

In `agent_factory.py`, import `build_sub_session_tools`, add parameters:

```python
    sub_session_runner=None,
    session_id: str | None = None,
```

after `max_depth`, and add:

```python
    tools.extend(
        build_sub_session_tools(
            spec, mode, sub_session_runner, session_id
        )
    )
```

after the existing `build_subagent_tools` extension.

- [ ] **Step 5: Add the runner to `Harness`**

In `harness.py`, replace `Harness.__init__` with:

```python
    def __init__(
        self,
        registry: ToolRegistry,
        model: Model,
        store_factory,
        sub_agents: dict[str, AgentSpec] | None = None,
        middleware: list[RunMiddleware] | None = None,
        compaction: CompactionConfig | None = None,
        sub_session_runner=None,
    ):
        self.registry = registry
        self.model = model
        self.store_factory = store_factory
        self.sub_agents = sub_agents or {}
        self.run_manager = RunManager()
        self.middleware = MiddlewarePipeline(
            middleware
            if middleware is not None
            else [CompactionMiddleware(compaction)]
        )
        self.sub_session_runner = sub_session_runner
```

Pass to `build_agent` in `run`:

```python
        agent = build_agent(
            spec,
            mode,
            self.registry,
            self.model,
            sub_agents=self.sub_agents,
            sub_session_runner=self.sub_session_runner,
            session_id=session.session_id,
        )
```

- [ ] **Step 6: Run tests, lint, types, and commit**

```bash
uv run pytest packages/agentbox-harness/tests/test_sub_session_tools.py -q
uv run pytest packages/agentbox-harness/tests/test_subagents.py -q
uv run ruff check --fix packages/agentbox-harness
uv run ty check packages/agentbox-harness
git add packages/agentbox-harness/src/agentbox_harness/subagents.py packages/agentbox-harness/src/agentbox_harness/agent_factory.py packages/agentbox-harness/src/agentbox_harness/harness.py packages/agentbox-harness/tests/test_sub_session_tools.py
git commit -m "feat(harness): sub-session tool protocol"
```

---

### Task 3: API runner core and prepare_agent wiring

**Files:**
- Create: `packages/agentbox-api/src/agentbox_api/subsessions.py`
- Modify: `packages/agentbox-api/src/agentbox_api/skills.py`
- Create: `packages/agentbox-api/tests/test_sub_sessions.py`

**Interfaces:**
- Produces: `SubSessionContext`, `ApiSubSessionRunner`; `PreparedAgent.sub_session_runner`; `prepare_agent(..., compaction=None, sub_session_depth=0)`.

- [ ] **Step 1: Write the failing runner tests**

Create `packages/agentbox-api/tests/test_sub_sessions.py`:

```python
import asyncio

from sqlmodel import select

from agentbox_api.skills import prepare_agent
from agentbox_api.subsessions import ApiSubSessionRunner, SubSessionContext
from agentbox_harness.compaction import CompactionConfig
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import Agent, Model, Project, Provider, SessionRow


async def _setup(tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(Provider(id="prov", name="prov", kind="test"))
        s.add(Model(id="m1", provider_id="prov", name="test-model"))
        s.add(
            Agent(
                id="parent-agent",
                name="parent",
                description="d",
                instructions="i",
                model_id="m1",
                sub_agent_ids='["child"]',
            )
        )
        s.add(
            Agent(
                id="child-agent",
                name="child",
                description="d",
                instructions="i",
                model_id="m1",
            )
        )
        s.add(Project(id="p1", name="p", path=str(tmp_path), owner_id="u1"))
        s.add(
            SessionRow(
                id="parent-session",
                project_id="p1",
                agent_id="parent-agent",
            )
        )
        await s.commit()
    return engine, factory


def _context(factory, tmp_path, depth=0):
    return SubSessionContext(
        factory=factory,
        project_root=str(tmp_path),
        skills_user_dir=str(tmp_path / "skills"),
        extra_roots=[],
        web_config=None,
        compaction=CompactionConfig(),
        media_max_dimension=1568,
        media_max_bytes=1_500_000,
        depth=depth,
    )


async def _prepared(factory, tmp_path):
    return await prepare_agent(
        factory,
        "parent",
        str(tmp_path),
        str(tmp_path / "skills"),
        session_id="parent-session",
    )


async def test_background_child_completes_and_reports_output(tmp_path):
    engine, factory = await _setup(tmp_path)
    try:
        prepared = await _prepared(factory, tmp_path)
        runner = ApiSubSessionRunner(_context(factory, tmp_path))
        started = await runner.start(
            "parent-session", prepared.spec, "child", "do work", wait=False
        )
        assert "Started sub-session" in started
        child_id = started.split()[2]
        for _ in range(50):
            output = await runner.get("parent-session", child_id, 4000)
            if "completed" in output:
                break
            await asyncio.sleep(0.1)
        assert "completed" in output
        assert "Hello from the test provider" in output
        assert "child" in await runner.list("parent-session")
    finally:
        await engine.dispose()


async def test_wait_true_returns_output(tmp_path):
    engine, factory = await _setup(tmp_path)
    try:
        prepared = await _prepared(factory, tmp_path)
        runner = ApiSubSessionRunner(_context(factory, tmp_path))
        output = await runner.start(
            "parent-session", prepared.spec, "child", "do work", wait=True
        )
        assert "completed" in output
        assert "Hello from the test provider" in output
    finally:
        await engine.dispose()


async def test_unknown_agent_empty_task_and_depth_limit(tmp_path):
    engine, factory = await _setup(tmp_path)
    try:
        prepared = await _prepared(factory, tmp_path)
        runner = ApiSubSessionRunner(_context(factory, tmp_path, depth=3))
        assert "maximum depth" in await runner.start(
            "parent-session", prepared.spec, "child", "x", False
        )
        shallow = ApiSubSessionRunner(_context(factory, tmp_path))
        assert "unknown agent" in await shallow.start(
            "parent-session", prepared.spec, "missing", "x", False
        )
        assert "must not be empty" in await shallow.start(
            "parent-session", prepared.spec, "child", "  ", False
        )
    finally:
        await engine.dispose()


async def test_child_agent_spec_gets_own_session_and_turns(tmp_path):
    engine, factory = await _setup(tmp_path)
    try:
        prepared = await _prepared(factory, tmp_path)
        runner = ApiSubSessionRunner(_context(factory, tmp_path))
        result = await runner.start(
            "parent-session", prepared.spec, "child", "work", wait=True
        )
        assert "child" in result
        async with factory() as s:
            children = (
                await s.execute(
                    select(SessionRow).where(
                        SessionRow.parent_session_id == "parent-session"
                    )
                )
            ).scalars().all()
        assert len(children) == 1
    finally:
        await engine.dispose()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/agentbox-api/tests/test_sub_sessions.py -q`

Expected: FAIL because `subsessions` and the runner are missing.

- [ ] **Step 3: Add `compaction` and `sub_session_depth` to `prepare_agent`**

In `skills.py`:

- import `CompactionConfig` from `agentbox_harness.compaction`;
- import `SubSessionRunner` from `agentbox_harness.subagents`;
- add `compaction: CompactionConfig | None = None` and
  `sub_session_depth: int = 0` after `extra_roots`;
- add `sub_session_runner: SubSessionRunner | None = None` to
  `PreparedAgent`;
- construct the runner lazily after `resolved_extra`/`web_config` are known:

```python
    from agentbox_api.subsessions import ApiSubSessionRunner, SubSessionContext

    sub_session_runner = ApiSubSessionRunner(
        SubSessionContext(
            factory=factory,
            project_root=project_root,
            skills_user_dir=user_dir,
            extra_roots=[str(path) for path in resolved_extra],
            web_config=web_config,
            compaction=compaction or CompactionConfig(),
            media_max_dimension=media_max_dimension,
            media_max_bytes=media_max_bytes,
            depth=sub_session_depth,
        )
    )
```

Return it in `PreparedAgent(..., sub_session_runner=sub_session_runner)`.

- [ ] **Step 4: Implement the API runner**

Create `subsessions.py`:

```python
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

from loguru import logger
from sqlmodel import select

from agentbox_api.skills import prepare_agent
from agentbox_harness.compaction import CompactionConfig
from agentbox_harness.events import EventBus
from agentbox_harness.harness import Harness
from agentbox_harness.run import Run
from agentbox_harness.session import Session, Turn
from agentbox_harness.spec import AgentSpec
from agentbox_harness.tools.web import WebToolConfig
from agentbox_harness.usage import context_tokens_from_usage
from agentbox_models.repos.message_log import SQLiteMessageLogStore
from agentbox_models.tables.core import Agent, SessionRow, TurnRow

MAX_SUB_SESSIONS = 5
MAX_SUB_SESSION_DEPTH = 3

_active: dict[str, tuple[asyncio.Task, Run]] = {}


@dataclass(frozen=True)
class SubSessionContext:
    factory: Any
    project_root: str
    skills_user_dir: str
    extra_roots: list[str]
    web_config: WebToolConfig | None
    compaction: CompactionConfig
    media_max_dimension: int
    media_max_bytes: int
    depth: int


async def _set_status(factory, child_id: str, status: str, error: str | None = None) -> None:
    async with factory() as s:
        row = await s.get(SessionRow, child_id)
        if row is not None:
            row.sub_session_status = status
            row.sub_session_error = error
            s.add(row)
            await s.commit()


async def _first_user_text(factory, child_id: str) -> str:
    async with factory() as s:
        row = (
            await s.execute(
                select(TurnRow)
                .where(TurnRow.session_id == child_id, TurnRow.role == "user")
                .order_by(TurnRow.created_at)
            )
        ).scalars().first()
    return row.content if row else ""


async def _latest_assistant_text(factory, child_id: str) -> str:
    async with factory() as s:
        row = (
            await s.execute(
                select(TurnRow)
                .where(TurnRow.session_id == child_id, TurnRow.role == "assistant")
                .order_by(TurnRow.created_at.desc())
            )
        ).scalars().first()
    return row.content if row else ""


async def _agent_name(factory, agent_id: str) -> str:
    async with factory() as s:
        row = await s.get(Agent, agent_id)
    return row.name if row else agent_id


class ApiSubSessionRunner:
    def __init__(self, context: SubSessionContext):
        self._context = context

    async def start(
        self,
        parent_session_id: str,
        parent_spec: AgentSpec,
        agent_name: str,
        task: str,
        wait: bool,
    ) -> str:
        if agent_name not in set(parent_spec.sub_agent_ids):
            return f"Sub-session failed: unknown agent {agent_name}."
        text = (task or "").strip()
        if not text:
            return "Sub-session failed: task must not be empty."
        if self._context.depth >= MAX_SUB_SESSION_DEPTH:
            return "Sub-session failed: maximum depth reached."

        async with self._context.factory() as s:
            parent = await s.get(SessionRow, parent_session_id)
            if parent is None:
                return "Sub-session failed: parent session not found."
            running = (
                await s.execute(
                    select(SessionRow).where(
                        SessionRow.parent_session_id == parent_session_id,
                        SessionRow.sub_session_status == "running",
                    )
                )
            ).scalars().all()
            project_id = parent.project_id
        if len(running) >= MAX_SUB_SESSIONS:
            return (
                f"Sub-session failed: at most {MAX_SUB_SESSIONS} children "
                "can run at once."
            )

        child_id = uuid.uuid4().hex
        try:
            prepared = await prepare_agent(
                self._context.factory,
                agent_name,
                self._context.project_root,
                self._context.skills_user_dir,
                session_id=child_id,
                session_mode="agent",
                media_max_dimension=self._context.media_max_dimension,
                media_max_bytes=self._context.media_max_bytes,
                web_config=self._context.web_config,
                extra_roots=self._context.extra_roots,
                compaction=self._context.compaction,
                sub_session_depth=self._context.depth + 1,
            )
        except (KeyError, ValueError) as exc:
            return f"Sub-session failed: {exc}"

        async with self._context.factory() as s:
            s.add(
                SessionRow(
                    id=child_id,
                    project_id=project_id,
                    agent_id=prepared.runtime.agent_id,
                    parent_session_id=parent_session_id,
                    sub_session_status="running",
                    sub_session_depth=self._context.depth + 1,
                )
            )
            await s.commit()

        store_factory = lambda: SQLiteMessageLogStore(self._context.factory, child_id)
        session = Session(
            session_id=child_id,
            project_root=self._context.project_root,
            agent_spec=prepared.spec,
            store=store_factory(),
            head_id=None,
            mode_name="agent",
        )
        harness = Harness(
            registry=prepared.registry,
            model=prepared.runtime.model,
            store_factory=store_factory,
            sub_session_runner=prepared.sub_session_runner,
            compaction=self._context.compaction,
        )
        bus = EventBus()
        try:
            run = await harness.run(session, text, bus)
        except Exception as exc:
            await _set_status(self._context.factory, child_id, "failed", str(exc))
            return f"Sub-session failed: {exc}"

        async def execute() -> str | None:
            try:
                outcome = await run.await_outcome()
                if outcome.status == "success":
                    result = await run.await_result()
                    context_tokens = context_tokens_from_usage(result.response.usage)
                    await session.append(
                        Turn(
                            id=uuid.uuid4().hex,
                            role="assistant",
                            content=str(result.output),
                            parent_id=session.head_id,
                            context_tokens=context_tokens,
                        ),
                        parent_id=session.head_id,
                    )
                    await _set_status(self._context.factory, child_id, "completed")
                    return str(result.output)
                if outcome.status == "cancelled":
                    run.cancel()
                    await _set_status(self._context.factory, child_id, "cancelled")
                    return None
                await _set_status(
                    self._context.factory,
                    child_id,
                    "failed",
                    outcome.message or "error",
                )
                return None
            except asyncio.CancelledError:
                run.cancel()
                await _set_status(self._context.factory, child_id, "cancelled")
                raise

        task_handle = asyncio.create_task(execute())
        _active[child_id] = (task_handle, run)
        task_handle.add_done_callback(lambda _: _active.pop(child_id, None))

        if wait:
            output = await task_handle
            async with self._context.factory() as s:
                row = await s.get(SessionRow, child_id)
            status = row.sub_session_status if row else "failed"
            if output:
                return f"Sub-session {child_id} {status} ({agent_name}): {output}"
            error = row.sub_session_error if row and row.sub_session_error else "no output"
            return f"Sub-session {child_id} {status} ({agent_name}): {error}"

        return f"Started sub-session {child_id} with {agent_name}."

    async def list(self, parent_session_id: str) -> str:
        async with self._context.factory() as s:
            rows = (
                await s.execute(
                    select(SessionRow)
                    .where(SessionRow.parent_session_id == parent_session_id)
                    .order_by(SessionRow.created_at)
                )
            ).scalars().all()
        if not rows:
            return "No sub-sessions."
        lines = ["Sub-sessions:"]
        for row in rows:
            if row.sub_session_status == "running" and row.id not in _active:
                await _set_status(
                    self._context.factory,
                    row.id,
                    "failed",
                    "interrupted by backend restart",
                )
                row.sub_session_status = "failed"
                row.sub_session_error = "interrupted by backend restart"
            task = await _first_user_text(self._context.factory, row.id)
            name = await _agent_name(self._context.factory, row.agent_id)
            lines.append(
                f"- {row.id} {row.sub_session_status or 'unknown'} "
                f"depth={row.sub_session_depth} agent={name} task={task[:80]}"
            )
        return "\n".join(lines)

    async def get(
        self, parent_session_id: str, sub_session_id: str, max_chars: int
    ) -> str:
        async with self._context.factory() as s:
            row = await s.get(SessionRow, sub_session_id)
        if row is None or row.parent_session_id != parent_session_id:
            return "Sub-session not found."
        if row.sub_session_status == "running" and sub_session_id not in _active:
            await _set_status(
                self._context.factory,
                sub_session_id,
                "failed",
                "interrupted by backend restart",
            )
            row.sub_session_status = "failed"
            row.sub_session_error = "interrupted by backend restart"
        limit = max(100, min(100_000, int(max_chars)))
        name = await _agent_name(self._context.factory, row.agent_id)
        task = await _first_user_text(self._context.factory, sub_session_id)
        output = await _latest_assistant_text(self._context.factory, sub_session_id)
        lines = [
            f"Sub-session {sub_session_id}: {row.sub_session_status or 'unknown'} "
            f"(agent {name}, depth {row.sub_session_depth})",
            f"Task: {task}",
        ]
        if row.sub_session_error:
            lines.append(f"Error: {row.sub_session_error}")
        lines.append("Output:")
        lines.append((output or "(no output)")[:limit])
        return "\n".join(lines)

    async def cancel(self, parent_session_id: str, sub_session_id: str) -> str:
        async with self._context.factory() as s:
            row = await s.get(SessionRow, sub_session_id)
        if row is None or row.parent_session_id != parent_session_id:
            return "Sub-session not found."
        if row.sub_session_status != "running":
            return f"Sub-session {sub_session_id} is already {row.sub_session_status}."
        active = _active.get(sub_session_id)
        if active is not None:
            task_handle, run = active
            run.cancel()
            task_handle.cancel()
        await _set_status(self._context.factory, sub_session_id, "cancelled")
        return f"Cancelled sub-session {sub_session_id}."


async def cancel_sub_sessions(factory, parent_session_id: str) -> None:
    async with factory() as s:
        rows = (
            await s.execute(
                select(SessionRow).where(
                    SessionRow.parent_session_id == parent_session_id,
                    SessionRow.sub_session_status == "running",
                )
            )
        ).scalars().all()
    for row in rows:
        active = _active.pop(row.id, None)
        if active is not None:
            task_handle, run = active
            run.cancel()
            task_handle.cancel()
        await _set_status(factory, row.id, "cancelled")


async def shutdown_sub_sessions() -> None:
    for child_id, (task_handle, run) in list(_active.items()):
        run.cancel()
        task_handle.cancel()
    _active.clear()


async def reconcile_running_sub_sessions(factory) -> None:
    async with factory() as s:
        rows = (
            await s.execute(
                select(SessionRow).where(SessionRow.sub_session_status == "running")
            )
        ).scalars().all()
        for row in rows:
            row.sub_session_status = "failed"
            row.sub_session_error = "interrupted by backend restart"
            s.add(row)
        await s.commit()
```

- [ ] **Step 5: Run the runner tests**

Run: `uv run pytest packages/agentbox-api/tests/test_sub_sessions.py -q`

Expected: PASS.

- [ ] **Step 6: Run lint, types, and commit**

```bash
uv run ruff check --fix packages
uv run ty check packages
git add packages/agentbox-api/src/agentbox_api/subsessions.py packages/agentbox-api/src/agentbox_api/skills.py packages/agentbox-api/tests/test_sub_sessions.py
git commit -m "feat(api): sub-session runner"
```

---

### Task 4: Wire the runner into Harness callers

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`
- Modify: `packages/agentbox-api/src/agentbox_api/acp_server.py`
- Modify: `packages/agentbox-api/src/agentbox_api/a2a_executor.py`
- Create: `packages/agentbox-api/tests/test_sub_session_wiring.py`

**Interfaces:**
- Consumes: `PreparedAgent.sub_session_runner`, `prepare_agent(compaction=..., sub_session_depth=...)`.
- Produces: parent chat/ACP/A2A agents receive the runner and compaction config.

- [ ] **Step 1: Write the failing wiring test**

Create `packages/agentbox-api/tests/test_sub_session_wiring.py`:

```python
from agentbox_api.skills import prepare_agent
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import Agent, Model, Provider


async def test_prepare_agent_returns_sub_session_runner(tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    try:
        async with factory() as s:
            s.add(Provider(id="prov", name="prov", kind="test"))
            s.add(Model(id="m1", provider_id="prov", name="test-model"))
            s.add(
                Agent(
                    id="ag",
                    name="bot",
                    description="d",
                    instructions="i",
                    model_id="m1",
                    sub_agent_ids='["child"]',
                )
            )
            await s.commit()
        prepared = await prepare_agent(
            factory,
            "bot",
            str(tmp_path),
            str(tmp_path / "skills"),
            session_id="s1",
        )
        assert prepared.sub_session_runner is not None
    finally:
        await engine.dispose()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest packages/agentbox-api/tests/test_sub_session_wiring.py -q`

Expected: FAIL if the runner field is missing.

- [ ] **Step 3: Pass the runner and compaction into chat**

In `routers/sessions.py` `prepare_agent` call add:

```python
            compaction=compaction_config_from_settings(request.app.state.settings),
```

In the `Harness(...)` call add:

```python
        sub_session_runner=prepared.sub_session_runner,
```

- [ ] **Step 4: Pass the runner and compaction into ACP and A2A**

In `acp_server.py`:

- both `prepare_agent` calls add
  `compaction=compaction_config_from_settings(self._settings)`;
- the `Harness(...)` call adds `sub_session_runner=prepared.sub_session_runner`.

In `a2a_executor.py`, do the same with `self._settings`.

- [ ] **Step 5: Run tests, lint, types, and commit**

```bash
uv run pytest packages/agentbox-api/tests/test_sub_session_wiring.py -q
uv run pytest packages/agentbox-api/tests/test_chat.py packages/agentbox-api/tests/test_acp.py packages/agentbox-api/tests/test_a2a.py -q
uv run ruff check --fix packages
uv run ty check packages
git add packages/agentbox-api/src/agentbox_api/routers/sessions.py packages/agentbox-api/src/agentbox_api/acp_server.py packages/agentbox-api/src/agentbox_api/a2a_executor.py packages/agentbox-api/tests/test_sub_session_wiring.py
git commit -m "feat(api): wire sub-session runner into sessions"
```

---

### Task 5: Lifecycle cleanup and limits

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/runtime.py`
- Modify: `packages/agentbox-api/src/agentbox_api/acp_server.py`
- Modify: `packages/agentbox-api/src/agentbox_api/app.py`
- Create: `packages/agentbox-api/tests/test_sub_session_lifecycle.py`

**Interfaces:**
- Consumes: `cancel_sub_sessions`, `shutdown_sub_sessions`, `reconcile_running_sub_sessions`.
- Produces: recursive parent deletion, ACP close cancellation, startup reconciliation, shutdown cancellation.

- [ ] **Step 1: Write the failing lifecycle tests**

Create `packages/agentbox-api/tests/test_sub_session_lifecycle.py`:

```python
from agentbox_api.runtime import delete_session_data
from agentbox_api.subsessions import (
    cancel_sub_sessions,
    reconcile_running_sub_sessions,
)
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import SessionRow


async def test_parent_delete_removes_children(tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    try:
        async with factory() as s:
            s.add(SessionRow(id="parent", project_id="p", agent_id="a"))
            s.add(
                SessionRow(
                    id="child",
                    project_id="p",
                    agent_id="b",
                    parent_session_id="parent",
                    sub_session_status="completed",
                    sub_session_depth=1,
                )
            )
            await s.commit()
        await delete_session_data(factory, "parent")
        async with factory() as s:
            assert await s.get(SessionRow, "parent") is None
            assert await s.get(SessionRow, "child") is None
    finally:
        await engine.dispose()


async def test_cancel_and_reconcile_running_children(tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    try:
        async with factory() as s:
            s.add(
                SessionRow(
                    id="child",
                    project_id="p",
                    agent_id="b",
                    parent_session_id="parent",
                    sub_session_status="running",
                    sub_session_depth=1,
                )
            )
            await s.commit()
        await cancel_sub_sessions(factory, "parent")
        async with factory() as s:
            assert (await s.get(SessionRow, "child")).sub_session_status == "cancelled"

        async with factory() as s:
            row = await s.get(SessionRow, "child")
            row.sub_session_status = "running"
            s.add(row)
            await s.commit()
        await reconcile_running_sub_sessions(factory)
        async with factory() as s:
            row = await s.get(SessionRow, "child")
        assert row.sub_session_status == "failed"
        assert "interrupted" in (row.sub_session_error or "")
    finally:
        await engine.dispose()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/agentbox-api/tests/test_sub_session_lifecycle.py -q`

Expected: FAIL because parent deletion does not remove children.

- [ ] **Step 3: Recursively delete children**

At the start of `delete_session_data` in `runtime.py`:

```python
    from agentbox_api.subsessions import cancel_sub_sessions

    await cancel_sub_sessions(factory, session_id)
    async with factory() as s:
        child_ids = [
            row.id
            for row in (
                await s.execute(
                    select(SessionRow).where(
                        SessionRow.parent_session_id == session_id
                    )
                )
            ).scalars().all()
        ]
    for child_id in child_ids:
        await delete_session_data(factory, child_id)
```

- [ ] **Step 4: Cancel children on ACP close and app lifecycle**

In `acp_server.py` `close_session`, lazily import and call:

```python
        from agentbox_api.subsessions import cancel_sub_sessions

        await cancel_sub_sessions(self._factory, session_id)
```

In `app.py` lifespan, after startup logging:

```python
        from agentbox_api.subsessions import reconcile_running_sub_sessions

        await reconcile_running_sub_sessions(session_factory)
```

and before engine disposal:

```python
        from agentbox_api.subsessions import shutdown_sub_sessions

        await shutdown_sub_sessions()
```

- [ ] **Step 5: Run tests, lint, types, and commit**

```bash
uv run pytest packages/agentbox-api/tests/test_sub_session_lifecycle.py -q
uv run pytest packages/agentbox-api/tests/test_session_delete.py packages/agentbox-api/tests/test_a2a.py -q
uv run ruff check --fix packages
uv run ty check packages
git add packages/agentbox-api/src/agentbox_api/runtime.py packages/agentbox-api/src/agentbox_api/acp_server.py packages/agentbox-api/src/agentbox_api/app.py packages/agentbox-api/tests/test_sub_session_lifecycle.py
git commit -m "feat(api): sub-session lifecycle cleanup"
```

---

### Task 6: Roadmap and full verification

**Files:**
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Update the roadmap**

Remove the `D8` row and add to the sub-project history:

```markdown
| 29 | Sub-agent sessions (background children, monitoring, cancellation) | `specs/2026-11-20-subagent-sessions-design.md` | `plans/2026-11-20-subagent-sessions.md` |
```

- [ ] **Step 2: Run the full verification**

```bash
uv run ruff check packages
uv run ty check packages
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-providers -q
uv run pytest packages/agentbox-api -q
cd apps/web && bun run test && bun run build
```

Expected: all checks pass.

- [ ] **Step 3: Commit the roadmap**

```bash
git add docs/ROADMAP.md
git commit -m "docs(roadmap): sub-agent sessions complete"
```
