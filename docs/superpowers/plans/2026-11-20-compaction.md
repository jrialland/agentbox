# Automatic Compaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add usage-driven automatic compaction with branch-aware summary turns, per-model context-window overrides, and reactive recovery, behind a harness middleware pipeline.

**Architecture:** A `RunMiddleware` pipeline wraps `Harness.run`; `CompactionMiddleware` uses response usage and the model profile/override to summarize old turns into a `summary` turn. Summary turns are inserted before retained turns, and history traversal stops at them. `RunManager` retries once on `ModelContextWindowExceededError`.

**Tech Stack:** Python 3.12, pydantic-ai 2.69 (`AgentRunResult`, `ModelProfile`, `ModelContextWindowExceededError`), SQLModel/Alembic, FastAPI, React/Mantine, Vitest.

## Global Constraints

- Context window: `model.profile["context_window"]` or explicit per-model override; never guess when neither is available.
- Proactive compaction uses `AgentRunResult.response.usage`, not pre-request token counting.
- Summary turns have `role="summary"`; history traversal stops at them; the first retained turn is rewired to the summary.
- Reactive recovery compacts and retries once on `ModelContextWindowExceededError`.
- Defaults: `compaction_enabled=True`, `compaction_ratio=0.8`, `compaction_keep_turns=4`, `compaction_input_budget_tokens=16000`, `compaction_max_summary_chars=8000`.
- The summarizer uses the agent's model with no tools.
- No full message-history rewrite; tool-call history remains out of scope.
- Run `ruff`/`ty` and the relevant tests before each commit.
- Regenerate `apps/web/openapi.json` and `apps/web/src/api/schema.d.ts` after backend schema changes.

---

### Task 1: Turn fields, summary-aware history, and schema migration

**Files:**
- Modify: `packages/agentbox-models/src/agentbox_models/tables/core.py`
- Create: `packages/agentbox-models/alembic/versions/b2c3d4e5f6a7_compaction_context.py`
- Create: `packages/agentbox-models/tests/test_compaction_fields.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/session.py`
- Modify: `packages/agentbox-models/src/agentbox_models/repos/message_log.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/messages.py`
- Create: `packages/agentbox-harness/tests/test_session_summary.py`

**Interfaces:**
- Produces: `Turn.context_tokens`, `Turn.created_at`, `MessageLogStore.set_parent`, `Session.insert_summary`, summary-aware `Session.history()` and `turns_to_messages`.

- [ ] **Step 1: Write the failing model roundtrip test**

Create `packages/agentbox-models/tests/test_compaction_fields.py`:

```python
from sqlmodel import select

from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import Model, Provider, TurnRow


async def test_compaction_fields_roundtrip():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    try:
        async with factory() as s:
            s.add(Provider(id="p1", name="p", kind="test"))
            s.add(
                Model(
                    id="m1",
                    provider_id="p1",
                    name="m",
                    context_window=128_000,
                )
            )
            s.add(
                TurnRow(
                    id="t1",
                    session_id="s1",
                    role="assistant",
                    content="x",
                    context_tokens=42,
                )
            )
            await s.commit()
        async with factory() as s:
            model = (await s.execute(select(Model).where(Model.id == "m1"))).scalars().first()
            turn = (await s.execute(select(TurnRow).where(TurnRow.id == "t1"))).scalars().first()
        assert model is not None and model.context_window == 128_000
        assert turn is not None and turn.context_tokens == 42
    finally:
        await engine.dispose()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest packages/agentbox-models/tests/test_compaction_fields.py -q`

Expected: FAIL because `Model`/`TurnRow` lack the fields.

- [ ] **Step 3: Add the columns and migration**

In `packages/agentbox-models/src/agentbox_models/tables/core.py`, add to `Model`:

```python
    context_window: int | None = None
```

Add to `TurnRow`:

```python
    context_tokens: int | None = None
```

Create `packages/agentbox-models/alembic/versions/b2c3d4e5f6a7_compaction_context.py`:

```python
"""compaction context fields

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-20 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("model", sa.Column("context_window", sa.Integer(), nullable=True))
    op.add_column("turnrow", sa.Column("context_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("turnrow", "context_tokens")
    op.drop_column("model", "context_window")
```

- [ ] **Step 4: Run the model test**

Run: `uv run pytest packages/agentbox-models/tests/test_compaction_fields.py -q`

Expected: PASS.

- [ ] **Step 5: Write the failing summary history tests**

Create `packages/agentbox-harness/tests/test_session_summary.py`:

```python
from pydantic_ai.messages import ModelRequest, UserPromptPart

from agentbox_harness.messages import turns_to_messages
from agentbox_harness.session import InMemoryMessageLogStore, Session, Turn


def _session() -> Session:
    return Session(
        session_id="s1",
        project_root=".",
        agent_spec=None,
        store=InMemoryMessageLogStore(),
        head_id=None,
    )


def _turn(id: str, role: str, content: str, context_tokens=None) -> Turn:
    return Turn(
        id=id,
        role=role,
        content=content,
        parent_id=None,
        context_tokens=context_tokens,
    )


async def test_summary_is_a_history_boundary_and_rewires_retained_turns():
    session = _session()
    t1 = _turn("t1", "user", "one")
    t2 = _turn("t2", "assistant", "two", context_tokens=900)
    t3 = _turn("t3", "user", "three")
    t4 = _turn("t4", "assistant", "four")
    for turn in (t1, t2, t3, t4):
        await session.append(turn, parent_id=session.head_id)

    summary = _turn("sum", "summary", "the summary")
    await session.insert_summary(summary, cutoff_id=t2.id, retained_first=t3)

    history = await session.history()
    assert [turn.id for turn in history] == ["sum", "t3", "t4"]
    assert (await session.store.get("sum")).parent_id == "t2"
    assert (await session.store.get("t3")).parent_id == "sum"
    assert session.head_id == "t4"


async def test_fork_before_summary_does_not_include_it():
    session = _session()
    t1 = _turn("t1", "user", "one")
    t2 = _turn("t2", "assistant", "two")
    t3 = _turn("t3", "user", "three")
    t4 = _turn("t4", "assistant", "four")
    for turn in (t1, t2, t3, t4):
        await session.append(turn, parent_id=session.head_id)
    await session.insert_summary(
        _turn("sum", "summary", "summary"), cutoff_id=t2.id, retained_first=t3
    )

    forked = Session(
        session_id="s1",
        project_root=".",
        agent_spec=None,
        store=session.store,
        head_id=t2.id,
    )
    assert [turn.id for turn in await forked.history()] == ["t1", "t2"]


def test_summary_role_maps_to_user_context():
    messages = turns_to_messages([_turn("sum", "summary", "compressed")])
    assert isinstance(messages[0], ModelRequest)
    part = messages[0].parts[0]
    assert isinstance(part, UserPromptPart)
    assert "Earlier conversation summary" in part.content
    assert "compressed" in part.content
```

- [ ] **Step 6: Run the summary tests to verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_session_summary.py -q`

Expected: FAIL because `insert_summary`/summary behavior is missing.

- [ ] **Step 7: Implement Turn fields, summary insertion, and history boundary**

In `session.py`:

```python
from dataclasses import dataclass, replace
from datetime import UTC, datetime
```

Add to `Turn`:

```python
    context_tokens: int | None = None
    created_at: datetime | None = None
```

Add to `MessageLogStore`:

```python
    async def set_parent(self, turn_id: str, parent_id: str) -> None: ...
```

Update `InMemoryMessageLogStore.append`:

```python
    async def append(self, turn: Turn) -> None:
        if turn.created_at is None:
            turn = replace(turn, created_at=datetime.now(UTC))
        self._turns[turn.id] = turn

    async def set_parent(self, turn_id: str, parent_id: str) -> None:
        turn = self._turns[turn_id]
        self._turns[turn_id] = replace(turn, parent_id=parent_id)
```

Add to `Session`:

```python
    async def append(self, turn: Turn, parent_id: str | None) -> None:
        turn = replace(turn, parent_id=parent_id)
        await self.store.append(turn)
        self.head_id = turn.id
        logger.debug("session turn appended session={} role={}", self.session_id, turn.role)

    async def insert_summary(
        self,
        summary: Turn,
        cutoff_id: str,
        retained_first: Turn | None,
    ) -> None:
        summary = replace(summary, parent_id=cutoff_id)
        await self.store.append(summary)
        if retained_first is not None:
            await self.store.set_parent(retained_first.id, summary.id)
        else:
            self.head_id = summary.id
```

Change `Session.history()` loop:

```python
            chain.append(current)
            if current.role == "summary" or current.parent_id is None:
                break
            current = await self.store.get(current.parent_id)
```

- [ ] **Step 8: Update the SQLite store and message mapping**

In `message_log.py`, import `utcnow`:

```python
from agentbox_models.tables.core import TurnRow, utcnow
```

Update `append`:

```python
            s.add(
                TurnRow(
                    id=turn.id,
                    session_id=self._session_id,
                    role=turn.role,
                    content=turn.content,
                    parent_id=turn.parent_id,
                    context_tokens=turn.context_tokens,
                    created_at=turn.created_at or utcnow(),
                )
            )
```

Map new fields in `list_turns` and `get`:

```python
            Turn(
                id=r.id,
                role=r.role,
                content=r.content,
                parent_id=r.parent_id,
                context_tokens=r.context_tokens,
                created_at=r.created_at,
            )
```

Add `set_parent`:

```python
    async def set_parent(self, turn_id: str, parent_id: str) -> None:
        async with self._factory() as s:
            row = await s.get(TurnRow, turn_id)
            if row is None:
                raise KeyError(turn_id)
            row.parent_id = parent_id
            s.add(row)
            await s.commit()
```

In `messages.py`, add:

```python
        elif turn.role == "summary":
            messages.append(
                ModelRequest(
                    parts=[
                        UserPromptPart(
                            content=(
                                "Earlier conversation summary:\n\n"
                                f"{turn.content}"
                            )
                        )
                    ]
                )
            )
```

- [ ] **Step 9: Make the messages endpoint summary-aware**

In `routers/sessions.py` `list_messages`, stop the chain walk at a summary
turn:

```python
    while cur is not None:
        chain.append(cur)
        if cur.role == "summary" or cur.parent_id is None:
            break
        cur = by_id.get(cur.parent_id) if cur.parent_id else None
```

Create `packages/agentbox-api/tests/test_compaction_messages.py`:

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
from agentbox_models.tables.core import TurnRow


async def test_messages_stop_at_summary():
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
        for row in (
            TurnRow(id="t1", session_id="s1", role="user", content="old question"),
            TurnRow(id="t2", session_id="s1", role="assistant", content="old answer", parent_id="t1"),
            TurnRow(id="sum", session_id="s1", role="summary", content="summary"),
            TurnRow(id="t3", session_id="s1", role="user", content="new question", parent_id="sum"),
            TurnRow(id="t4", session_id="s1", role="assistant", content="new answer", parent_id="t3"),
        ):
            s.add(row)
        await s.commit()

    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    try:
        login = await client.post(
            "/auth/login", json={"username": "alice", "password": "pw"}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        response = await client.get("/sessions/s1/messages", headers=headers)
        assert response.status_code == 200
        assert [(m["id"], m["role"]) for m in response.json()] == [
            ("sum", "summary"),
            ("t3", "user"),
            ("t4", "assistant"),
        ]
    finally:
        await client.aclose()
        await engine.dispose()
```

- [ ] **Step 10: Run tests, lint, types, and commit**

```bash
uv run pytest packages/agentbox-models/tests/test_compaction_fields.py -q
uv run pytest packages/agentbox-harness/tests/test_session_summary.py -q
uv run pytest packages/agentbox-api/tests/test_compaction_messages.py -q
uv run ruff check --fix packages
uv run ty check packages
git add packages/agentbox-models/src/agentbox_models/tables/core.py packages/agentbox-models/alembic/versions/b2c3d4e5f6a7_compaction_context.py packages/agentbox-models/tests/test_compaction_fields.py packages/agentbox-harness/src/agentbox_harness/session.py packages/agentbox-models/src/agentbox_models/repos/message_log.py packages/agentbox-harness/src/agentbox_harness/messages.py packages/agentbox-harness/tests/test_session_summary.py packages/agentbox-api/src/agentbox_api/routers/sessions.py packages/agentbox-api/tests/test_compaction_messages.py
git commit -m "feat(harness): summary-aware turn history"
```

---

### Task 2: Model context-window override and model API

**Files:**
- Modify: `packages/agentbox-providers/src/agentbox_providers/resolver.py`
- Modify: `packages/agentbox-providers/tests/test_resolver.py`
- Modify: `packages/agentbox-api/src/agentbox_api/runtime.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/models.py`
- Modify: `packages/agentbox-api/tests/test_provider_model_admin.py`

**Interfaces:**
- Produces: `resolve_model(provider, model_name, context_window=None)`; `ModelCreate.context_window`/`ModelRead.context_window`.

- [ ] **Step 1: Write the failing resolver tests**

Append to `packages/agentbox-providers/tests/test_resolver.py`:

```python
def test_resolve_context_window_override():
    m = resolve_model(
        Provider(id="p", name="openai", kind="openai_legacy", api_key="sk-test"),
        "custom-model",
        context_window=123_456,
    )
    assert m.profile["context_window"] == 123_456


def test_resolve_known_model_profile_is_used_without_override():
    m = resolve_model(
        Provider(id="p", name="openai", kind="openai_legacy", api_key="sk-test"),
        "gpt-4o",
    )
    assert m.profile["context_window"] == 128_000
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/agentbox-providers/tests/test_resolver.py -q`

Expected: FAIL because `resolve_model` has no `context_window` parameter.

- [ ] **Step 3: Implement the resolver override**

Change the signature and add a profile helper:

```python
def resolve_model(
    provider: Provider, model_name: str, context_window: int | None = None
) -> Model:
    profile = {"context_window": context_window} if context_window else None
```

Pass `profile=profile` to every model constructor (`OpenAIChatModel`,
`OpenAIResponsesModel`, `AnthropicModel`, `OllamaModel`, `TestModel`).

In `runtime.resolve_agent_runtime`, pass `model.context_window`:

```python
        model=resolve_model(provider, model.name, model.context_window),
```

- [ ] **Step 4: Write the failing model API test**

In `packages/agentbox-api/tests/test_provider_model_admin.py`, change the create
payload in `test_model_create_duplicate_and_delete` to:

```python
        r = await client.post(
            "/models",
            json={
                "provider_id": "prov",
                "name": "m2",
                "context_window": 200_000,
            },
            headers=h,
        )
        assert r.status_code == 200
        assert r.json()["context_window"] == 200_000
```

- [ ] **Step 5: Run it to verify it fails**

Run: `uv run pytest packages/agentbox-api/tests/test_provider_model_admin.py -q`

Expected: FAIL because `ModelCreate`/`ModelRead` do not expose `context_window`.

- [ ] **Step 6: Add context_window to the model API**

In `routers/models.py`, add to `ModelCreate` and `ModelRead`:

```python
    context_window: int | None = None
```

Include it in `model_read`:

```python
        context_window=model.context_window,
```

Set it on create:

```python
        model = Model(
            id=uuid.uuid4().hex,
            provider_id=body.provider_id,
            name=body.name,
            context_window=body.context_window,
        )
```

- [ ] **Step 7: Run tests, lint, types, and commit**

```bash
uv run pytest packages/agentbox-providers/tests/test_resolver.py -q
uv run pytest packages/agentbox-api/tests/test_provider_model_admin.py -q
uv run ruff check --fix packages
uv run ty check packages
git add packages/agentbox-providers/src/agentbox_providers/resolver.py packages/agentbox-providers/tests/test_resolver.py packages/agentbox-api/src/agentbox_api/runtime.py packages/agentbox-api/src/agentbox_api/routers/models.py packages/agentbox-api/tests/test_provider_model_admin.py
git commit -m "feat(providers): model context window override"
```

---

### Task 3: Middleware pipeline and compaction middleware

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/middleware.py`
- Create: `packages/agentbox-harness/tests/test_middleware.py`
- Create: `packages/agentbox-harness/src/agentbox_harness/compaction.py`
- Create: `packages/agentbox-harness/tests/test_compaction.py`

**Interfaces:**
- Produces: `RunContext`, `RunMiddleware`, `MiddlewarePipeline`, `CompactionConfig`, `CompactionMiddleware`.

- [ ] **Step 1: Write the failing middleware tests**

Create `packages/agentbox-harness/tests/test_middleware.py`:

```python
from pydantic_ai.messages import ModelMessage

from agentbox_harness.events import EventBus
from agentbox_harness.middleware import MiddlewarePipeline, RunContext
from agentbox_harness.session import InMemoryMessageLogStore, Session


def _ctx() -> RunContext:
    session = Session(
        session_id="s1",
        project_root=".",
        agent_spec=None,
        store=InMemoryMessageLogStore(),
        head_id=None,
    )
    return RunContext(session=session, model=None, bus=EventBus(), prompt="hi")


class Fake:
    def __init__(self, name, history=None):
        self.name = name
        self.calls = []
        self.history = history

    async def before_run(self, ctx):
        self.calls.append("before")

    async def on_context_overflow(self, ctx) -> list[ModelMessage] | None:
        self.calls.append("recover")
        return self.history


async def test_prepare_runs_before_run_in_order():
    first, second = Fake("first"), Fake("second")
    pipeline = MiddlewarePipeline([first, second])
    await pipeline.prepare(_ctx())
    assert first.calls == ["before"]
    assert second.calls == ["before"]


async def test_recover_returns_first_non_none():
    first = Fake("first", history=[])
    second = Fake("second", history=[])
    pipeline = MiddlewarePipeline([first, second])
    assert await pipeline.recover(_ctx()) == []
    assert first.calls == ["recover"]
    assert second.calls == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_middleware.py -q`

Expected: FAIL with `ModuleNotFoundError` for `middleware`.

- [ ] **Step 3: Implement the middleware pipeline**

Create `middleware.py`:

```python
from dataclasses import dataclass, field
from typing import Protocol

from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model

from agentbox_harness.errors import RunOutcome
from agentbox_harness.events import EventBus
from agentbox_harness.session import Session


@dataclass
class RunContext:
    session: Session
    model: Model
    bus: EventBus
    prompt: str
    prompt_override: list | None = None
    message_history: list[ModelMessage] = field(default_factory=list)
    outcome: RunOutcome | None = None


class RunMiddleware(Protocol):
    async def before_run(self, ctx: RunContext) -> None: ...

    async def on_context_overflow(
        self, ctx: RunContext
    ) -> list[ModelMessage] | None: ...


class MiddlewarePipeline:
    def __init__(self, middleware: list[RunMiddleware] | None = None):
        self._middleware = list(middleware or [])

    async def prepare(self, ctx: RunContext) -> None:
        for item in self._middleware:
            await item.before_run(ctx)

    async def recover(self, ctx: RunContext) -> list[ModelMessage] | None:
        for item in self._middleware:
            history = await item.on_context_overflow(ctx)
            if history is not None:
                ctx.message_history = history
                return history
        return None
```

- [ ] **Step 4: Run the middleware tests**

Run: `uv run pytest packages/agentbox-harness/tests/test_middleware.py -q`

Expected: PASS.

- [ ] **Step 5: Write the failing compaction tests**

Create `packages/agentbox-harness/tests/test_compaction.py`:

```python
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.models.test import TestModel

from agentbox_harness.compaction import CompactionConfig, CompactionMiddleware
from agentbox_harness.events import EventBus
from agentbox_harness.messages import turns_to_messages
from agentbox_harness.middleware import RunContext
from agentbox_harness.session import InMemoryMessageLogStore, Session, Turn


async def _session_with_history() -> Session:
    session = Session(
        session_id="s1",
        project_root=".",
        agent_spec=None,
        store=InMemoryMessageLogStore(),
        head_id=None,
    )
    for index in range(6):
        role = "user" if index % 2 == 0 else "assistant"
        await session.append(
            Turn(
                id=f"t{index}",
                role=role,
                content=f"turn {index}",
                parent_id=None,
                context_tokens=900 if role == "assistant" else None,
            ),
            parent_id=session.head_id,
        )
    return session


def _ctx(session: Session, window: int | None = 1000) -> RunContext:
    profile = {"context_window": window} if window else None
    model = TestModel(custom_output_text="SUMMARY", profile=profile)
    return RunContext(
        session=session,
        model=model,
        bus=EventBus(),
        prompt="next",
    )


async def test_before_run_compacts_above_threshold():
    session = await _session_with_history()
    ctx = _ctx(session)
    middleware = CompactionMiddleware(
        CompactionConfig(keep_turns=2, input_budget_tokens=100_000)
    )
    await middleware.before_run(ctx)

    history = await session.history()
    assert history[0].role == "summary"
    assert history[0].content == "SUMMARY"
    assert [turn.id for turn in history[1:]] == ["t4", "t5"]


async def test_second_run_skips_when_summary_is_newer_than_usage():
    session = await _session_with_history()
    ctx = _ctx(session)
    middleware = CompactionMiddleware(
        CompactionConfig(keep_turns=2, input_budget_tokens=100_000)
    )
    await middleware.before_run(ctx)
    await middleware.before_run(ctx)
    history = await session.history()
    assert sum(1 for turn in history if turn.role == "summary") == 1


async def test_no_window_or_disabled_does_not_compact():
    session = await _session_with_history()
    ctx = _ctx(session, window=None)
    middleware = CompactionMiddleware(CompactionConfig(keep_turns=2))
    await middleware.before_run(ctx)
    assert all(turn.role != "summary" for turn in await session.history())

    ctx = _ctx(session)
    disabled = CompactionMiddleware(CompactionConfig(enabled=False))
    await disabled.before_run(ctx)
    assert all(turn.role != "summary" for turn in await session.history())


async def test_force_compaction_works_without_window():
    session = await _session_with_history()
    ctx = _ctx(session, window=None)
    middleware = CompactionMiddleware(CompactionConfig(keep_turns=2))
    history = await middleware.on_context_overflow(ctx)
    assert history is not None
    assert (await session.history())[0].role == "summary"


async def test_summary_maps_to_user_context():
    session = await _session_with_history()
    ctx = _ctx(session)
    middleware = CompactionMiddleware(
        CompactionConfig(keep_turns=2, input_budget_tokens=100_000)
    )
    await middleware.before_run(ctx)
    messages = turns_to_messages(await session.history())
    assert isinstance(messages[0], ModelRequest)
    part = messages[0].parts[0]
    assert isinstance(part, UserPromptPart)
    assert "Earlier conversation summary" in part.content
```

- [ ] **Step 6: Run them to verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_compaction.py -q`

Expected: FAIL with `ModuleNotFoundError` for `compaction`.

- [ ] **Step 7: Implement compaction**

Create `compaction.py`:

```python
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from loguru import logger
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model

from agentbox_harness.messages import turns_to_messages
from agentbox_harness.middleware import RunContext
from agentbox_harness.session import Turn

SUMMARY_SYSTEM_PROMPT = """You compress conversation history for an AI coding agent.
Produce a concise summary under these headings: Goal, Decisions, Work completed,
Files and commands, Current state, Open tasks. Preserve exact file paths, commands,
errors, identifiers, and user constraints. Do not invent details. Output only the
summary."""


@dataclass(frozen=True)
class CompactionConfig:
    enabled: bool = True
    ratio: float = 0.8
    keep_turns: int = 4
    input_budget_tokens: int = 16_000
    max_summary_chars: int = 8_000


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _latest_usage(history: list[Turn]) -> Turn | None:
    for turn in reversed(history):
        if turn.role == "assistant" and turn.context_tokens is not None:
            return turn
    return None


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _summary_after(history: list[Turn], usage: Turn) -> bool:
    usage_time = _as_utc(usage.created_at)
    if usage_time is None:
        return False
    for turn in history:
        if turn.role != "summary":
            continue
        summary_time = _as_utc(turn.created_at)
        if summary_time is not None and summary_time > usage_time:
            return True
    return False


def _format_turn(turn: Turn) -> str:
    return f"[{turn.role}]\n{turn.content}"


class CompactionMiddleware:
    def __init__(self, config: CompactionConfig | None = None):
        self.config = config or CompactionConfig()

    async def before_run(self, ctx: RunContext) -> None:
        if not self.config.enabled:
            return
        window = ctx.model.profile.get("context_window")
        if not window:
            return
        history = await ctx.session.history()
        usage = _latest_usage(history)
        if usage is None or usage.context_tokens is None:
            return
        if _summary_after(history, usage):
            return
        if usage.context_tokens < int(window * self.config.ratio):
            return
        await self.compact(ctx)

    async def on_context_overflow(
        self, ctx: RunContext
    ) -> list[ModelMessage] | None:
        if not self.config.enabled:
            return None
        return await self.compact(ctx)

    async def compact(self, ctx: RunContext) -> list[ModelMessage] | None:
        history = await ctx.session.history()
        keep = max(0, self.config.keep_turns)
        candidates = history[:-keep] if keep else list(history)
        if not candidates:
            return None

        window = ctx.model.profile.get("context_window")
        budget = self.config.input_budget_tokens
        if window:
            budget = min(budget, max(1_000, window // 2))

        selected: list[Turn] = []
        used = 0
        for turn in candidates:
            cost = _estimate_tokens(turn.content)
            if selected and used + cost > budget:
                break
            selected.append(turn)
            used += cost
        if not selected:
            return None

        cutoff = selected[-1]
        retained_first = history[len(selected)] if len(history) > len(selected) else None
        text = "\n\n".join(_format_turn(turn) for turn in selected)
        if len(text) > budget * 4:
            text = text[: budget * 4] + "\n\n[truncated]"

        summary = await self._summarize(ctx.model, text)
        if not summary:
            return None
        summary = summary[: self.config.max_summary_chars]
        summary_turn = Turn(
            id=uuid.uuid4().hex,
            role="summary",
            content=summary,
            parent_id=cutoff.id,
            created_at=datetime.now(UTC),
        )
        await ctx.session.insert_summary(summary_turn, cutoff.id, retained_first)
        result = turns_to_messages(await ctx.session.history())
        ctx.message_history = result
        return result

    async def _summarize(self, model: Model, text: str) -> str | None:
        try:
            agent = Agent(model, system_prompt=SUMMARY_SYSTEM_PROMPT)
            result = await agent.run(text)
            return str(result.output).strip() or None
        except Exception:
            logger.exception("compaction summarization failed")
            return None
```

- [ ] **Step 8: Run compaction tests**

Run: `uv run pytest packages/agentbox-harness/tests/test_compaction.py -q`

Expected: PASS.

- [ ] **Step 9: Run lint, types, and commit**

```bash
uv run ruff check --fix packages/agentbox-harness
uv run ty check packages/agentbox-harness
git add packages/agentbox-harness/src/agentbox_harness/middleware.py packages/agentbox-harness/tests/test_middleware.py packages/agentbox-harness/src/agentbox_harness/compaction.py packages/agentbox-harness/tests/test_compaction.py
git commit -m "feat(harness): compaction middleware"
```

---

### Task 4: Harness pipeline integration, retry, and usage helper

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/usage.py`
- Create: `packages/agentbox-harness/tests/test_usage.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/errors.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/run.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/harness.py`
- Create: `packages/agentbox-harness/tests/test_run_retry.py`

**Interfaces:**
- Produces: `context_tokens_from_usage`, `RunOutcome.code`, `RunManager` context retry, `Harness.middleware`.

- [ ] **Step 1: Write the failing usage/retry tests**

Create `packages/agentbox-harness/tests/test_usage.py`:

```python
from pydantic_ai.usage import RequestUsage

from agentbox_harness.usage import context_tokens_from_usage


def test_context_tokens_from_measured_usage():
    usage = RequestUsage(input_tokens=10, output_tokens=5)
    assert context_tokens_from_usage(usage) == 15


def test_context_tokens_from_unmeasured_usage():
    assert context_tokens_from_usage(RequestUsage()) is None
```

Create `packages/agentbox-harness/tests/test_run_retry.py`:

```python
from contextlib import asynccontextmanager

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelContextWindowExceededError
from pydantic_ai.models.test import TestModel

from agentbox_harness.events import EventBus
from agentbox_harness.run import RunManager


class FlakyModel(TestModel):
    def __init__(self):
        super().__init__(custom_output_text="ok")
        self.calls = 0

    @asynccontextmanager
    async def request_stream(
        self, messages, model_settings, model_request_parameters, run_context=None
    ):
        self.calls += 1
        if self.calls == 1:
            raise ModelContextWindowExceededError("test", "too long")
        async with super().request_stream(
            messages,
            model_settings,
            model_request_parameters,
            run_context=run_context,
        ) as response:
            yield response


async def test_run_retries_once_on_context_overflow():
    model = FlakyModel()
    agent = Agent(model)
    bus = EventBus()
    recoveries = 0

    async def recover():
        nonlocal recoveries
        recoveries += 1
        return []

    run = RunManager().start(
        agent,
        "hi",
        "r1",
        bus,
        on_context_overflow=recover,
    )
    result = await run.await_result()
    assert result is not None
    assert model.calls == 2
    assert recoveries == 1
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_usage.py packages/agentbox-harness/tests/test_run_retry.py -q`

Expected: FAIL with missing `usage` module and no `on_context_overflow` parameter.

- [ ] **Step 3: Add the usage helper**

Create `usage.py`:

```python
from pydantic_ai.usage import RequestUsage


def context_tokens_from_usage(usage: RequestUsage) -> int | None:
    return usage.total_tokens if usage.has_values() else None
```

- [ ] **Step 4: Add the outcome code**

In `errors.py`:

```python
from pydantic_ai.exceptions import ModelContextWindowExceededError, RunCancelled
```

Update `RunOutcome`:

```python
    code: str | None = None
```

Update `normalize_error`:

```python
    if isinstance(exc, ModelContextWindowExceededError):
        return RunOutcome(
            status="error",
            message=str(exc),
            code="context_window",
        )
```

- [ ] **Step 5: Add the retry to RunManager**

Replace `RunManager`'s `start` and `_drive` with:

```python
from pydantic_ai.exceptions import ModelContextWindowExceededError


class RunManager:
    def start(
        self,
        agent: Agent,
        prompt: str,
        run_id: str,
        bus: EventBus,
        model_override=None,
        cancellation_token: CancellationToken | None = None,
        message_history=None,
        prompt_override=None,
        on_context_overflow=None,
    ) -> Run:
        task = asyncio.create_task(
            self._drive(
                agent,
                prompt,
                run_id,
                bus,
                model_override,
                cancellation_token,
                message_history,
                prompt_override,
                on_context_overflow,
            )
        )
        return Run(run_id=run_id, task=task, cancellation_token=cancellation_token)

    async def _drive(
        self,
        agent: Agent,
        prompt: str,
        run_id: str,
        bus: EventBus,
        model_override=None,
        cancellation_token: CancellationToken | None = None,
        message_history=None,
        prompt_override=None,
        on_context_overflow=None,
    ):
        seq = 0
        prompt_arg = prompt_override if prompt_override is not None else prompt
        base_kwargs = {"model": model_override} if model_override is not None else {}
        if cancellation_token is not None:
            base_kwargs["cancellation_token"] = cancellation_token

        async def attempt(history):
            nonlocal seq
            kwargs = dict(base_kwargs)
            if history is not None:
                kwargs["message_history"] = history
            final = None
            async with agent.run_stream_events(prompt_arg, **kwargs) as events:
                async for event in events:
                    bus.publish(RunEvent(run_id=run_id, seq=seq, event=event))
                    seq += 1
                    if isinstance(event, AgentRunResultEvent):
                        final = event.result
            return final

        try:
            return await attempt(message_history)
        except ModelContextWindowExceededError as exc:
            if on_context_overflow is None:
                logger.exception("run failed id={}", run_id)
                bus.publish(
                    RunEvent(run_id=run_id, seq=seq, event=normalize_error(exc))
                )
                raise
            try:
                new_history = await on_context_overflow()
            except BaseException:
                logger.exception("context recovery failed id={}", run_id)
                bus.publish(
                    RunEvent(run_id=run_id, seq=seq, event=normalize_error(exc))
                )
                raise exc
            if new_history is None:
                logger.exception("run failed id={}", run_id)
                bus.publish(
                    RunEvent(run_id=run_id, seq=seq, event=normalize_error(exc))
                )
                raise
            try:
                return await attempt(new_history)
            except BaseException as retry_exc:
                logger.exception("run failed id={}", run_id)
                bus.publish(
                    RunEvent(
                        run_id=run_id,
                        seq=seq,
                        event=normalize_error(retry_exc),
                    )
                )
                raise
        except BaseException as exc:
            logger.exception("run failed id={}", run_id)
            bus.publish(
                RunEvent(run_id=run_id, seq=seq, event=normalize_error(exc))
            )
            raise
```

- [ ] **Step 6: Integrate the pipeline into Harness**

In `harness.py`:

```python
from agentbox_harness.compaction import CompactionConfig, CompactionMiddleware
from agentbox_harness.middleware import (
    MiddlewarePipeline,
    RunContext,
    RunMiddleware,
)
from agentbox_harness.usage import context_tokens_from_usage
```

Replace `Harness.__init__` and `Harness.run` with:

```python
    def __init__(
        self,
        registry: ToolRegistry,
        model: Model,
        store_factory,
        sub_agents: dict[str, AgentSpec] | None = None,
        middleware: list[RunMiddleware] | None = None,
        compaction: CompactionConfig | None = None,
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

    async def run(
        self,
        session: Session,
        user_message: str,
        bus: EventBus,
        model_override=None,
        prompt_override=None,
    ) -> Run:
        model = model_override or self.model
        context = RunContext(
            session=session,
            model=model,
            bus=bus,
            prompt=user_message,
            prompt_override=prompt_override,
        )
        await self.middleware.prepare(context)

        turn = Turn(
            id=uuid.uuid4().hex,
            role="user",
            content=user_message,
            parent_id=session.head_id,
        )
        await session.append(turn, parent_id=session.head_id)
        message_history = turns_to_messages(await session.history())

        mode = self._resolve_mode(session)
        spec = session.agent_spec
        if spec is None:
            raise ValueError("Session has no agent spec")
        logger.debug(
            "harness run start agent={} mode={} session={}",
            spec.name,
            mode.name,
            session.session_id,
        )
        agent = build_agent(
            spec,
            mode,
            self.registry,
            self.model,
            sub_agents=self.sub_agents,
        )
        return self.run_manager.start(
            agent,
            user_message,
            run_id=uuid.uuid4().hex,
            bus=bus,
            model_override=model_override,
            message_history=message_history,
            prompt_override=prompt_override,
            on_context_overflow=lambda: self.middleware.recover(context),
        )
```

Update `run_turn` assistant turn:

```python
            context_tokens = context_tokens_from_usage(result.response.usage)
            turn = Turn(
                id=uuid.uuid4().hex,
                role="assistant",
                content=str(result.output),
                parent_id=session.head_id,
                context_tokens=context_tokens,
            )
```

- [ ] **Step 7: Run the harness tests**

Run: `uv run pytest packages/agentbox-harness/tests/test_usage.py packages/agentbox-harness/tests/test_run_retry.py packages/agentbox-harness/tests/test_compaction.py packages/agentbox-harness/tests/test_session_summary.py -q`

Expected: PASS.

- [ ] **Step 8: Run the whole harness suite, lint, types, and commit**

```bash
uv run pytest packages/agentbox-harness -q
uv run ruff check --fix packages/agentbox-harness
uv run ty check packages/agentbox-harness
git add packages/agentbox-harness/src/agentbox_harness/usage.py packages/agentbox-harness/tests/test_usage.py packages/agentbox-harness/src/agentbox_harness/errors.py packages/agentbox-harness/src/agentbox_harness/run.py packages/agentbox-harness/src/agentbox_harness/harness.py packages/agentbox-harness/tests/test_run_retry.py
git commit -m "feat(harness): compaction pipeline and context retry"
```

---

### Task 5: API settings and turn usage wiring

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/config.py`
- Modify: `packages/agentbox-api/src/agentbox_api/runtime.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`
- Modify: `packages/agentbox-api/src/agentbox_api/acp_server.py`
- Modify: `packages/agentbox-api/src/agentbox_api/a2a_executor.py`
- Create: `packages/agentbox-api/tests/test_compaction_wiring.py`

**Interfaces:**
- Consumes: `CompactionConfig`, `context_tokens_from_usage`.
- Produces: `compaction_config_from_settings`, compaction settings, assistant `context_tokens`.

- [ ] **Step 1: Write the failing wiring test**

Create `packages/agentbox-api/tests/test_compaction_wiring.py`:

```python
from agentbox_api.config import Settings
from agentbox_api.runtime import compaction_config_from_settings


def test_compaction_config_from_settings():
    settings = Settings(
        jwt_secret="s" * 32,
        compaction_enabled=False,
        compaction_ratio=0.7,
        compaction_keep_turns=6,
        compaction_input_budget_tokens=12_000,
        compaction_max_summary_chars=4_000,
    )
    config = compaction_config_from_settings(settings)
    assert config.enabled is False
    assert config.ratio == 0.7
    assert config.keep_turns == 6
    assert config.input_budget_tokens == 12_000
    assert config.max_summary_chars == 4_000
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest packages/agentbox-api/tests/test_compaction_wiring.py -q`

Expected: FAIL because the settings/helper are missing.

- [ ] **Step 3: Add settings and the config helper**

In `config.py`, add after the web settings:

```python
    compaction_enabled: bool = True
    compaction_ratio: float = 0.8
    compaction_keep_turns: int = 4
    compaction_input_budget_tokens: int = 16_000
    compaction_max_summary_chars: int = 8_000
```

In `runtime.py`, import `CompactionConfig` and add:

```python
def compaction_config_from_settings(settings) -> CompactionConfig:
    return CompactionConfig(
        enabled=settings.compaction_enabled,
        ratio=settings.compaction_ratio,
        keep_turns=settings.compaction_keep_turns,
        input_budget_tokens=settings.compaction_input_budget_tokens,
        max_summary_chars=settings.compaction_max_summary_chars,
    )
```

- [ ] **Step 4: Wire compaction and context tokens into chat**

In `routers/sessions.py`, import `compaction_config_from_settings` and
`context_tokens_from_usage`. Add to `Harness(...)`:

```python
        compaction=compaction_config_from_settings(request.app.state.settings),
```

Set the assistant turn:

```python
                context_tokens = context_tokens_from_usage(result.response.usage)
                turn = Turn(
                    id=uuid.uuid4().hex,
                    role="assistant",
                    content=str(result.output),
                    parent_id=session.head_id,
                    context_tokens=context_tokens,
                )
```

- [ ] **Step 5: Wire ACP and A2A**

In `acp_server.py`:

- import `compaction_config_from_settings`, `context_tokens_from_usage`;
- `Harness(..., compaction=compaction_config_from_settings(self._settings))`;
- assistant turn gets `context_tokens=context_tokens_from_usage(result.response.usage)`;
- in `load_session`, skip `turn.role == "summary"` when replaying turns to the
  IDE client (the model still uses them).

In `a2a_executor.py`, do the same Harness/turn wiring with `self._settings`.

- [ ] **Step 6: Run tests, lint, types, and commit**

```bash
uv run pytest packages/agentbox-api/tests/test_compaction_wiring.py -q
uv run pytest packages/agentbox-api/tests/test_chat.py packages/agentbox-api/tests/test_acp.py packages/agentbox-api/tests/test_a2a.py -q
uv run ruff check --fix packages
uv run ty check packages
git add packages/agentbox-api/src/agentbox_api/config.py packages/agentbox-api/src/agentbox_api/runtime.py packages/agentbox-api/src/agentbox_api/routers/sessions.py packages/agentbox-api/src/agentbox_api/acp_server.py packages/agentbox-api/src/agentbox_api/a2a_executor.py packages/agentbox-api/tests/test_compaction_wiring.py
git commit -m "feat(api): compaction settings and turn usage"
```

---

### Task 6: Frontend model context window and summary notice

**Files:**
- Regenerate: `apps/web/openapi.json`, `apps/web/src/api/schema.d.ts`
- Modify: `apps/web/src/api/endpoints.ts`
- Modify: `apps/web/src/pages/ProvidersPage.tsx`
- Create: `apps/web/src/chat/SummaryNotice.tsx`
- Create: `apps/web/src/chat/SummaryNotice.test.tsx`
- Modify: `apps/web/src/pages/SessionPage.tsx`
- Modify: `apps/web/src/pages/SessionPage.test.tsx`

- [ ] **Step 1: Regenerate the API artifacts**

```bash
uv run python apps/web/scripts/gen-openapi.py
cd apps/web && bun run codegen
```

- [ ] **Step 2: Update the model client and form**

In `endpoints.ts`, add `context_window?: number` to the `createModel` body.

In `ProvidersPage.tsx` `ModelsTab`:

- add `const [contextWindow, setContextWindow] = useState<number | string>("");`
- add a `NumberInput` labeled `Context window` (min 1);
- include `context_window: contextWindow === "" ? undefined : Number(contextWindow)` in `create.mutateAsync`;
- add a `Context window` table column.

Add a small form test in `ProvidersPage.test.tsx` or keep the existing render
test; if adding a test, assert `screen.getByLabelText("Context window")` is
present after selecting the Models tab.

- [ ] **Step 3: Create the summary notice**

`apps/web/src/chat/SummaryNotice.tsx`:

```tsx
import { Button } from "@mantine/core";
import { useState } from "react";

import { MarkdownBlock } from "./MarkdownBlock";

export function SummaryNotice({ content }: { content: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="box" data-testid="summary-notice" style={{ marginBottom: "0.75rem" }}>
      <div className="is-flex is-justify-content-space-between is-align-items-center">
        <strong>Earlier conversation summarized</strong>
        <Button size="compact-xs" variant="subtle" onClick={() => setOpen((v) => !v)}>
          {open ? "Hide" : "Show"}
        </Button>
      </div>
      {open && <MarkdownBlock content={content} />}
    </div>
  );
}
```

- [ ] **Step 4: Render summary turns in SessionPage**

Import `SummaryNotice`. In the messages map, branch on the role:

```tsx
          {(messages ?? []).map((m) =>
            m.role === "summary" ? (
              <SummaryNotice key={m.id} content={m.content} />
            ) : (
              <div key={m.id} className={`session-turn session-turn-${m.role}`}>
                <div className="is-flex is-justify-content-space-between">
                  <p className="is-size-7 has-text-grey">{m.role}</p>
                  {m.role === "user" && (
                    <Button
                      size="compact-xs"
                      variant="subtle"
                      onClick={() => {
                        setInput(m.content);
                        setForkMode(true);
                        setForkFromTurnId(m.parent_id ?? null);
                      }}
                    >
                      Edit
                    </Button>
                  )}
                </div>
                {m.role === "assistant" ? (
                  <MarkdownBlock content={m.content} />
                ) : (
                  <pre className="session-content">{m.content}</pre>
                )}
              </div>
            ),
          )}
```

- [ ] **Step 5: Add the frontend tests**

`SummaryNotice.test.tsx`:

```tsx
import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";

import { SummaryNotice } from "./SummaryNotice";

test("renders and expands the summary", () => {
  render(
    <MantineProvider>
      <SummaryNotice content="compressed history" />
    </MantineProvider>,
  );
  expect(screen.getByText("Earlier conversation summarized")).toBeInTheDocument();
  expect(screen.queryByText("compressed history")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show" }));
  expect(screen.getByText("compressed history")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Hide" })).toBeInTheDocument();
});
```

Add a SessionPage test with a mocked summary message:

```tsx
test("renders a summary notice", async () => {
  vi.spyOn(endpoints, "fetchMessages").mockResolvedValue([
    { id: "sum", role: "summary", content: "compressed", parent_id: null },
  ] as never);
  vi.spyOn(endpoints, "fetchSession").mockResolvedValue({ agent_name: "bot" } as never);
  // render the same tree as the existing test
  expect(await screen.findByText("Earlier conversation summarized")).toBeInTheDocument();
});
```

- [ ] **Step 6: Run frontend tests and build**

```bash
cd apps/web
bun run test
bun run build
```

- [ ] **Step 7: Commit**

```bash
git add apps/web/openapi.json apps/web/src/api/schema.d.ts apps/web/src/api/endpoints.ts apps/web/src/pages/ProvidersPage.tsx apps/web/src/chat/SummaryNotice.tsx apps/web/src/chat/SummaryNotice.test.tsx apps/web/src/pages/SessionPage.tsx apps/web/src/pages/SessionPage.test.tsx
git commit -m "feat(web): context window and summary notice"
```

---

### Task 7: Roadmap and full verification

**Files:**
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Update the roadmap**

Remove the `D10` row and add to the sub-project history:

```markdown
| 28 | Automatic compaction (usage-driven summaries + context-window recovery) | `specs/2026-11-20-compaction-design.md` | `plans/2026-11-20-compaction.md` |
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
git commit -m "docs(roadmap): automatic compaction complete"
```
