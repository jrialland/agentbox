# Model Labels and Label-Based Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add normalized model labels, per-link priority, label CRUD-by-assignment, and agents that bind to a label and re-resolve to a model at load time.

**Architecture:** `Label` + `ModelLabelLink` tables in `agentbox-models`, a reusable `resolve_model_label(session, label, provider=None)` resolver, `ModelRead` API responses, and a `model_label` field on `AgentSpec`/`Agent` that `AgentRepository` re-resolves on load while keeping the `model_id` snapshot.

**Tech Stack:** Python 3.12, uv, SQLModel, Alembic, FastAPI, loguru, pytest (asyncio auto), React/TypeScript, Mantine, react-query, Playwright.

## Global Constraints

- Label names are canonicalised as `" ".join(name.strip().lower().split())`; reject empty and names > 40 chars.
- Resolution order: `priority ASC`, then `Provider.name ASC`, then `Model.name ASC`.
- Existing agents without `model_label` keep current behaviour; `Agent.model_id` stays non-null.
- Reads use `providers:read`; label assignment and model writes use `providers:create`; model/provider delete keeps `providers:delete`.
- Label deletion/rename is out of scope; labels are created implicitly by assignment.
- Never log secrets or file contents.
- Regenerate `apps/web/openapi.json` + `apps/web/src/api/schema.d.ts` after API changes.
- Run `uv run ruff check packages`, `uv run ty check packages`, and relevant tests before each commit.

---

### Task 1: Label tables and resolver (models package)

**Files:**
- Modify: `packages/agentbox-models/src/agentbox_models/tables/core.py`
- Create: `packages/agentbox-models/src/agentbox_models/repos/model_labels.py`
- Test: `packages/agentbox-models/tests/test_model_labels.py`

**Interfaces:**
- Produces: `Label(id, name)`, `ModelLabelLink(model_id, label_id, priority)`, `canonical_label(name: str) -> str`, `resolve_model_label(session, label: str, provider: str | None = None) -> Model | None`.

- [ ] **Step 1: Write failing tests**

Create `test_model_labels.py`:

```python
import pytest

from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.repos.model_labels import canonical_label, resolve_model_label
from agentbox_models.tables.core import Label, Model, ModelLabelLink, Provider


async def _db():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    return engine, factory


def test_canonical_label():
    assert canonical_label("  Fast  ") == "fast"
    assert canonical_label("High   End") == "high end"
    assert canonical_label("   ") == ""


async def test_resolve_model_label_priority_and_provider_tiebreak():
    engine, factory = await _db()
    try:
        async with factory() as s:
            s.add(Provider(id="p1", name="alpha", kind="test"))
            s.add(Provider(id="p2", name="beta", kind="test"))
            s.add(Model(id="m1", provider_id="p1", name="slow"))
            s.add(Model(id="m2", provider_id="p2", name="cheap"))
            s.add(Model(id="m3", provider_id="p2", name="fast"))
            s.add(Label(id="l", name="fast"))
            s.add(ModelLabelLink(model_id="m1", label_id="l", priority=0))
            s.add(ModelLabelLink(model_id="m2", label_id="l", priority=1))
            s.add(ModelLabelLink(model_id="m3", label_id="l", priority=1))
            await s.commit()

            resolved = await resolve_model_label(s, " FAST ")
            assert resolved is not None and resolved.id == "m1"

            await s.delete((await s.get(ModelLabelLink, ("m1", "l"))))
            await s.commit()
            resolved = await resolve_model_label(s, "fast")
            assert resolved is not None and resolved.id == "m2"
    finally:
        await engine.dispose()


async def test_resolve_unknown_label_returns_none():
    engine, factory = await _db()
    try:
        async with factory() as s:
            assert await resolve_model_label(s, "missing") is None
    finally:
        await engine.dispose()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/agentbox-models/tests/test_model_labels.py -q`
Expected: FAIL (`ModuleNotFoundError`/`ImportError`).

- [ ] **Step 3: Implement**

Append to `tables/core.py` after `Model`:

```python
class Label(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str = Field(index=True, unique=True)


class ModelLabelLink(SQLModel, table=True):
    model_id: str = Field(foreign_key="model.id", primary_key=True)
    label_id: str = Field(foreign_key="label.id", primary_key=True)
    priority: int = 0
```

Create `repos/model_labels.py`:

```python
from sqlmodel import select

from agentbox_models.tables.core import Label, Model, ModelLabelLink, Provider

MAX_LABEL_LENGTH = 40


def canonical_label(name: str) -> str:
    return " ".join(name.strip().lower().split())


async def resolve_model_label(session, label: str, provider: str | None = None):
    canonical = canonical_label(label)
    if not canonical or len(canonical) > MAX_LABEL_LENGTH:
        return None
    statement = (
        select(Model)
        .join(ModelLabelLink, ModelLabelLink.model_id == Model.id)
        .join(Label, Label.id == ModelLabelLink.label_id)
        .join(Provider, Provider.id == Model.provider_id)
        .where(Label.name == canonical)
        .order_by(
            ModelLabelLink.priority.asc(),
            Provider.name.asc(),
            Model.name.asc(),
        )
    )
    if provider is not None:
        statement = statement.where(Provider.name == provider)
    return (await session.execute(statement)).scalars().first()
```

`ModelLabelLink` has a composite primary key, so `s.get(ModelLabelLink, ("m1", "l"))` works with SQLModel/SQLAlchemy ordering `(model_id, label_id)`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest packages/agentbox-models -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-models/src/agentbox_models/tables/core.py packages/agentbox-models/src/agentbox_models/repos/model_labels.py packages/agentbox-models/tests/test_model_labels.py
git commit -m "feat(models): add labels and label resolver"
```

---

### Task 2: Alembic migration

**Files:**
- Create: `packages/agentbox-models/alembic/versions/c4f8e2a1b9d3_model_labels.py`

**Interfaces:**
- Consumes: table/column names from Task 1.
- Produces: migration head after `7a1c2f3d4e5b`.

- [ ] **Step 1: Write the migration**

```python
"""model labels

Revision ID: c4f8e2a1b9d3
Revises: 7a1c2f3d4e5b
Create Date: 2026-11-19 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4f8e2a1b9d3"
down_revision: str | Sequence[str] | None = "7a1c2f3d4e5b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "label",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
    )
    op.create_index("ix_label_name", "label", ["name"], unique=True)
    op.create_table(
        "modellabellink",
        sa.Column("model_id", sa.String(), sa.ForeignKey("model.id"), primary_key=True),
        sa.Column("label_id", sa.String(), sa.ForeignKey("label.id"), primary_key=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("agent", sa.Column("model_label", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent", "model_label")
    op.drop_table("modellabellink")
    op.drop_index("ix_label_name", table_name="label")
    op.drop_table("label")
```

- [ ] **Step 2: Apply the migration to a scratch database**

```bash
$env:DATABASE_URL="sqlite+aiosqlite:///./tmp-migrate.db"
uv run alembic -c packages/agentbox-models/alembic.ini upgrade head
Remove-Item ./tmp-migrate.db
```

Expected: `Running upgrade 7a1c2f3d4e5b -> c4f8e2a1b9d3`.

If `env.py` does not read `DATABASE_URL`, run the same command with the project's configured DB and inspect the output.

- [ ] **Step 3: Verify tables are importable**

```bash
uv run python -c "from agentbox_models.tables.core import Agent, Label, ModelLabelLink; print(Agent.model_label, Label.__tablename__, ModelLabelLink.__tablename__)"
```

Expected: prints the column and `label modellabellink`.

- [ ] **Step 4: Commit**

```bash
git add packages/agentbox-models/alembic/versions/c4f8e2a1b9d3_model_labels.py
git commit -m "feat(models): migrate model labels"
```

---

### Task 3: Labels and model-read API

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/routers/models.py`
- Create: `packages/agentbox-api/src/agentbox_api/routers/labels.py`
- Modify: `packages/agentbox-api/src/agentbox_api/app.py:12-22,54-64`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/providers.py`
- Test: `packages/agentbox-api/tests/test_model_labels.py`

**Interfaces:**
- Produces: `ModelRead { id, provider_id, name, labels: [{ id, name, priority }] }`, `LabelRead { id, name }`, `model_read(session, model) -> ModelRead`, `PUT /models/{mid}/labels`, `GET /labels`.

- [ ] **Step 1: Write failing API tests**

Create `test_model_labels.py`:

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
from agentbox_models.tables.core import Model, ModelLabelLink, Provider
from sqlmodel import select


async def _setup():
    perms = (
        "providers:create",
        "providers:read",
        "providers:delete",
        "agents:create",
        "agents:read",
    )
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r1", name="role"))
        for i, p in enumerate(perms):
            s.add(Permission(id=f"p{i}", name=p))
            s.add(RolePermissionLink(role_id="r1", permission_id=f"p{i}"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(Provider(id="prov", name="prov", kind="test"))
        s.add(Model(id="m1", provider_id="prov", name="alpha"))
        s.add(Model(id="m2", provider_id="prov", name="beta"))
        await s.commit()
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    return engine, client, factory


async def _auth(client) -> dict:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_assign_labels_case_folded_and_listed():
    engine, client, _ = await _setup()
    try:
        h = await _auth(client)
        r = await client.put(
            "/models/m1/labels",
            json={
                "labels": [
                    {"label": " Fast ", "priority": 5},
                    {"label": "fast", "priority": 2},
                ]
            },
            headers=h,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "alpha"
        assert body["labels"] == [
            {"id": body["labels"][0]["id"], "name": "fast", "priority": 2}
        ]

        r = await client.get("/labels", headers=h)
        assert r.status_code == 200
        assert [label["name"] for label in r.json()] == ["fast"]

        r = await client.get("/models", headers=h)
        alpha = next(m for m in r.json() if m["id"] == "m1")
        assert [label["name"] for label in alpha["labels"]] == ["fast"]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_model_with_labels():
    engine, client, _ = await _setup()
    try:
        h = await _auth(client)
        r = await client.post(
            "/models",
            json={
                "provider_id": "prov",
                "name": "gamma",
                "labels": [{"label": "cheap", "priority": 1}],
            },
            headers=h,
        )
        assert r.status_code == 200
        assert [label["name"] for label in r.json()["labels"]] == ["cheap"]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_delete_model_and_provider_remove_links():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        await client.put(
            "/models/m1/labels", json={"labels": [{"label": "fast"}]}, headers=h
        )
        assert (await client.delete("/models/m1", headers=h)).status_code == 200
        async with factory() as s:
            links = (await s.execute(select(ModelLabelLink))).scalars().all()
            assert links == []

        await client.put(
            "/models/m2/labels", json={"labels": [{"label": "fast"}]}, headers=h
        )
        assert (await client.delete("/providers/prov", headers=h)).status_code == 200
        async with factory() as s:
            assert (await s.execute(select(ModelLabelLink))).scalars().all() == []
    finally:
        await client.aclose()
        await engine.dispose()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/agentbox-api/tests/test_model_labels.py -q`
Expected: FAIL (`404` on `/labels`, missing `labels` in responses).

- [ ] **Step 3: Implement the models router**

Replace `routers/models.py` with:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_models.repos.model_labels import MAX_LABEL_LENGTH, canonical_label
from agentbox_models.tables.core import Agent, Label, Model, ModelLabelLink, Provider

router = APIRouter(prefix="/models", tags=["models"])


class LabelAssignment(BaseModel):
    label: str
    priority: int = 0


class ModelLabelRead(BaseModel):
    id: str
    name: str
    priority: int


class ModelCreate(BaseModel):
    provider_id: str
    name: str
    labels: list[LabelAssignment] = []


class ModelLabelsUpdate(BaseModel):
    labels: list[LabelAssignment] = []


class ModelRead(BaseModel):
    id: str
    provider_id: str
    name: str
    labels: list[ModelLabelRead] = []


async def model_read(s, model: Model) -> ModelRead:
    rows = (
        await s.execute(
            select(Label, ModelLabelLink.priority)
            .join(ModelLabelLink, ModelLabelLink.label_id == Label.id)
            .where(ModelLabelLink.model_id == model.id)
            .order_by(Label.name)
        )
    ).all()
    return ModelRead(
        id=model.id,
        provider_id=model.provider_id,
        name=model.name,
        labels=[
            ModelLabelRead(id=label.id, name=label.name, priority=priority)
            for label, priority in rows
        ],
    )


async def replace_labels(s, model_id: str, assignments: list[LabelAssignment]) -> None:
    existing = (
        await s.execute(
            select(ModelLabelLink).where(ModelLabelLink.model_id == model_id)
        )
    ).scalars().all()
    for link in existing:
        await s.delete(link)
    wanted: dict[str, int] = {}
    for assignment in assignments:
        name = canonical_label(assignment.label)
        if not name or len(name) > MAX_LABEL_LENGTH:
            raise HTTPException(status_code=400, detail="Invalid label name")
        wanted[name] = assignment.priority
    for name, priority in wanted.items():
        label = (
            await s.execute(select(Label).where(Label.name == name))
        ).scalars().first()
        if label is None:
            label = Label(id=uuid.uuid4().hex, name=name)
            s.add(label)
            await s.flush()
        s.add(ModelLabelLink(model_id=model_id, label_id=label.id, priority=priority))


@router.get("", response_model=list[ModelRead])
async def list_models_endpoint(
    request: Request, _=Depends(require_permission("providers:read"))
):
    async with request.app.state.session_factory() as s:
        models = (await s.execute(select(Model))).scalars().all()
        return [await model_read(s, model) for model in models]


@router.post("", response_model=ModelRead)
async def create_model(
    body: ModelCreate,
    request: Request,
    _=Depends(require_permission("providers:create")),
):
    async with request.app.state.session_factory() as s:
        provider = (
            await s.execute(select(Provider).where(Provider.id == body.provider_id))
        ).scalars().first()
        if provider is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        dup = (
            await s.execute(
                select(Model).where(
                    Model.provider_id == body.provider_id, Model.name == body.name
                )
            )
        ).scalars().first()
        if dup is not None:
            raise HTTPException(status_code=409, detail="Model already exists")
        model = Model(id=uuid.uuid4().hex, provider_id=body.provider_id, name=body.name)
        s.add(model)
        await s.flush()
        if body.labels:
            await replace_labels(s, model.id, body.labels)
        await s.commit()
        logger.info("model created provider={} name={}", model.provider_id, model.name)
        result = await model_read(s, model)
    return result


@router.put("/{mid}/labels", response_model=ModelRead)
async def set_model_labels(
    mid: str,
    body: ModelLabelsUpdate,
    request: Request,
    _=Depends(require_permission("providers:create")),
):
    async with request.app.state.session_factory() as s:
        model = (await s.execute(select(Model).where(Model.id == mid))).scalars().first()
        if model is None:
            raise HTTPException(status_code=404, detail="Not found")
        await replace_labels(s, mid, body.labels)
        await s.commit()
        result = await model_read(s, model)
    return result


@router.delete("/{mid}")
async def delete_model(
    mid: str, request: Request, _=Depends(require_permission("providers:create"))
):
    async with request.app.state.session_factory() as s:
        model = (await s.execute(select(Model).where(Model.id == mid))).scalars().first()
        if model is None:
            raise HTTPException(status_code=404, detail="Not found")
        in_use = (
            await s.execute(select(Agent).where(Agent.model_id == mid))
        ).scalars().first()
        if in_use is not None:
            raise HTTPException(status_code=409, detail="Model in use")
        links = (
            await s.execute(
                select(ModelLabelLink).where(ModelLabelLink.model_id == mid)
            )
        ).scalars().all()
        for link in links:
            await s.delete(link)
        await s.delete(model)
        await s.commit()
        logger.info("model deleted id={}", mid)
    return {"ok": True}
```

Create `routers/labels.py`:

```python
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_models.tables.core import Label

router = APIRouter(prefix="/labels", tags=["labels"])


class LabelRead(BaseModel):
    id: str
    name: str


@router.get("", response_model=list[LabelRead])
async def list_labels(
    request: Request, _=Depends(require_permission("providers:read"))
):
    async with request.app.state.session_factory() as s:
        rows = (await s.execute(select(Label).order_by(Label.name))).scalars().all()
    return [LabelRead(id=row.id, name=row.name) for row in rows]
```

In `app.py`, add `from agentbox_api.routers.labels import router as labels_router` and `app.include_router(labels_router)`.

- [ ] **Step 4: Update provider cascade + refresh models**

In `routers/providers.py`:

1. Import `from agentbox_api.routers.models import ModelRead, model_read` and `from agentbox_models.tables.core import ModelLabelLink`.
2. `refresh_models` response becomes `list[ModelRead]` and the final block becomes:

```python
    async with factory() as s:
        rows = (
            await s.execute(select(Model).where(Model.provider_id == pid))
        ).scalars().all()
        return [await model_read(s, row) for row in rows]
```

3. In `delete_provider`, before `for model in models:`, delete links:

```python
        if model_ids:
            links = (
                await s.execute(
                    select(ModelLabelLink).where(
                        ModelLabelLink.model_id.in_(model_ids)  # ty: ignore[missing-attribute]
                    )
                )
            ).scalars().all()
            for link in links:
                await s.delete(link)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest packages/agentbox-api/tests/test_model_labels.py packages/agentbox-api/tests/test_provider_model_admin.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/agentbox-api/src/agentbox_api/routers/models.py packages/agentbox-api/src/agentbox_api/routers/labels.py packages/agentbox-api/src/agentbox_api/app.py packages/agentbox-api/src/agentbox_api/routers/providers.py packages/agentbox-api/tests/test_model_labels.py
git commit -m "feat(api): model labels endpoints and label-aware model reads"
```

---

### Task 4: Agent label binding and dynamic re-resolution

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/spec.py`
- Modify: `packages/agentbox-models/src/agentbox_models/repos/agents.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/agents.py`
- Test: append to `packages/agentbox-api/tests/test_model_labels.py`

**Interfaces:**
- Consumes: `canonical_label`, `resolve_model_label` (Task 1).
- Produces: `AgentSpec.model_label`, save/load re-resolution, `AgentCreate.model_label`, exactly-one validation.

- [ ] **Step 1: Write failing tests**

Append to `test_model_labels.py`:

```python
async def test_agent_binds_to_label_and_reresolves():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        await client.put(
            "/models/m1/labels", json={"labels": [{"label": "fast", "priority": 10}]}, headers=h
        )
        await client.put(
            "/models/m2/labels", json={"labels": [{"label": "fast", "priority": 1}]}, headers=h
        )
        r = await client.post(
            "/agents", json={"name": "a", "model_label": "fast"}, headers=h
        )
        assert r.status_code == 200
        body = r.json()
        assert body["model_label"] == "fast"
        assert body["model_binding"]["model"] == "beta"

        await client.put(
            "/models/m1/labels", json={"labels": [{"label": "fast", "priority": 1}]}, headers=h
        )
        await client.put(
            "/models/m2/labels", json={"labels": [{"label": "fast", "priority": 10}]}, headers=h
        )
        r = await client.get("/agents", headers=h)
        agent = next(a for a in r.json() if a["name"] == "a")
        assert agent["model_binding"]["model"] == "alpha"
    finally:
        await client.aclose()
        await engine.dispose()


async def test_agent_requires_exactly_one_model_reference():
    engine, client, _ = await _setup()
    try:
        h = await _auth(client)
        assert (
            await client.post("/agents", json={"name": "none"}, headers=h)
        ).status_code == 400
        assert (
            await client.post(
                "/agents",
                json={"name": "both", "model": "alpha", "model_label": "fast"},
                headers=h,
            )
        ).status_code == 400
        assert (
            await client.post(
                "/agents", json={"name": "bad", "model_label": "missing"}, headers=h
            )
        ).status_code == 400
    finally:
        await client.aclose()
        await engine.dispose()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/agentbox-api/tests/test_model_labels.py -q -k agent`
Expected: FAIL (`model_label` unsupported / 500).

- [ ] **Step 3: Implement `AgentSpec` + repository**

In `spec.py`, append `model_label: str | None = None` to `AgentSpec`.

In `repos/agents.py`, add imports:

```python
from agentbox_models.repos.model_labels import canonical_label, resolve_model_label
```

Replace `save` with:

```python
    async def save(self, spec: AgentSpec) -> AgentSpec:
        async with self._factory() as s:
            label = canonical_label(spec.model_label) if spec.model_label else None
            if label:
                model = await resolve_model_label(s, label)
                if model is None:
                    raise ValueError(f"No model for label: {label}")
            else:
                model = (
                    await s.execute(
                        select(Model).where(Model.name == spec.model_binding.model)
                    )
                ).scalars().first()
                if model is None:
                    raise ValueError(f"Unknown model: {spec.model_binding.model}")
            provider = (
                await s.execute(select(Provider).where(Provider.id == model.provider_id))
            ).scalars().first()

            existing = (
                await s.execute(select(Agent).where(Agent.name == spec.name))
            ).scalars().first()
            row = existing or Agent(
                id=uuid.uuid4().hex,
                name=spec.name,
                description="",
                instructions="",
                model_id=model.id,
            )
            row.description = spec.description
            row.instructions = spec.instructions
            row.model_id = model.id
            row.model_label = label
            row.tool_bindings = _serialize_bindings(spec.tool_bindings)
            row.mode_definitions = _serialize_modes(spec.mode_definitions)
            row.sub_agent_ids = json.dumps(spec.sub_agent_ids)
            s.add(row)
            await s.commit()
            logger.info("agent saved name={}", spec.name)
        return spec.model_copy(
            update={
                "model_binding": ModelBinding(model=model.name, provider=provider.name),
                "model_label": label,
            }
        )
```

Replace the model lookup in `load` with:

```python
            model = None
            if row.model_label:
                model = await resolve_model_label(s, row.model_label)
            if model is None:
                model = (
                    await s.execute(select(Model).where(Model.id == row.model_id))
                ).scalars().first()
            if model is None:
                raise ValueError(f"Unknown model for agent: {name}")
            provider = (
                await s.execute(select(Provider).where(Provider.id == model.provider_id))
            ).scalars().first()
            return AgentSpec(
                name=row.name,
                description=row.description,
                instructions=row.instructions,
                tool_bindings=_parse_bindings(row.tool_bindings),
                mode_definitions=_parse_modes(row.mode_definitions),
                sub_agent_ids=json.loads(row.sub_agent_ids or "[]"),
                model_binding=ModelBinding(model=model.name, provider=provider.name),
                model_label=row.model_label,
            )
```

- [ ] **Step 4: Implement `AgentCreate`**

In `routers/agents.py`:

```python
class AgentCreate(BaseModel):
    name: str
    description: str = ""
    instructions: str = ""
    model: str | None = None
    model_label: str | None = None
    tool_bindings: list[dict] = []
    mode_definitions: list[dict] = []
    sub_agent_ids: list[str] = []
```

In `_to_spec`, use `model_binding=ModelBinding(model=body.model or "", provider=""), model_label=body.model_label`.

In `create_agent`:

```python
    if bool(body.model) == bool(body.model_label):
        raise HTTPException(
            status_code=400,
            detail="Exactly one of model or model_label is required",
        )
    repo = AgentRepository(request.app.state.session_factory)
    try:
        spec = await repo.save(_to_spec(body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest packages/agentbox-api/tests/test_model_labels.py packages/agentbox-api/tests/test_agents_router.py packages/agentbox-api/tests/test_chat.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/spec.py packages/agentbox-models/src/agentbox_models/repos/agents.py packages/agentbox-api/src/agentbox_api/routers/agents.py packages/agentbox-api/tests/test_model_labels.py
git commit -m "feat(api): bind agents to labels with live re-resolution"
```

---

### Task 5: Web types, endpoints, and queries

**Files:**
- Regenerate: `apps/web/openapi.json`, `apps/web/src/api/schema.d.ts`
- Modify: `apps/web/src/api/endpoints.ts`
- Modify: `apps/web/src/api/queries.ts`

**Interfaces:**
- Consumes: Task 3/4 API.
- Produces: `fetchLabels`, `setModelLabels`, `useLabels`, `useSetModelLabels`, updated `Model`/`createAgent`/`createModel` types.

- [ ] **Step 1: Regenerate the schema**

```bash
uv run python apps/web/scripts/gen-openapi.py
cd apps/web && bun run codegen
```

Expected: `openapi.json` and `schema.d.ts` include `ModelRead`, `LabelRead`, `model_label`.

- [ ] **Step 2: Update endpoints**

In `endpoints.ts`:

```ts
export type Model = components["schemas"]["ModelRead"];
export type Label = components["schemas"]["LabelRead"];

export async function fetchLabels(): Promise<Label[]> {
  const { data } = await api.GET("/labels");
  return data ?? [];
}

export async function setModelLabels(
  mid: string,
  labels: { label: string; priority: number }[],
): Promise<Model> {
  const { data, error } = await api.PUT("/models/{mid}/labels", {
    params: { path: { mid } },
    body: { labels },
  });
  if (error) throw new Error("Failed to set labels");
  return data as Model;
}
```

Update `createModel` body to `labels?: { label: string; priority: number }[]`, and `createAgent` body to:

```ts
  model?: string;
  model_label?: string;
```

- [ ] **Step 3: Update queries**

In `queries.ts`, import `fetchLabels`, `setModelLabels` and add:

```ts
export function useLabels() {
  return useQuery({ queryKey: ["labels"], queryFn: fetchLabels });
}

export function useSetModelLabels() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      mid: string;
      labels: { label: string; priority: number }[];
    }) => setModelLabels(input.mid, input.labels),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["models"] });
      void qc.invalidateQueries({ queryKey: ["labels"] });
    },
  });
}
```

- [ ] **Step 4: Typecheck**

Run: `bun run build` (workdir `apps/web`)
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/openapi.json apps/web/src/api/schema.d.ts apps/web/src/api/endpoints.ts apps/web/src/api/queries.ts
git commit -m "feat(web): label API client and queries"
```

---

### Task 6: Models tab labels UI

**Files:**
- Modify: `apps/web/src/pages/ProvidersPage.tsx`
- Test: covered by Task 7 E2E; keep `bun run build` green.

**Interfaces:**
- Consumes: `Model.labels`, `useLabels`, `useSetModelLabels`.
- Produces: labels column, label filter, “Edit labels” modal.

- [ ] **Step 1: Update imports and `ModelsTab`**

In `ProvidersPage.tsx`, import `useEffect` from `react`; add `Badge`, `Group`, `NumberInput` to the Mantine import; import `useLabels`, `useSetModelLabels` from `../api/queries`.

Add a modal component above `ModelsTab`:

```tsx
function ModelLabelsModal({
  model,
  opened,
  onClose,
}: {
  model: Model | null;
  opened: boolean;
  onClose: () => void;
}) {
  const { data: labels } = useLabels();
  const setLabels = useSetModelLabels();
  const [rows, setRows] = useState<{ label: string; priority: number }[]>([]);

  useEffect(() => {
    setRows(model ? model.labels.map((l) => ({ label: l.name, priority: l.priority })) : []);
  }, [model]);

  async function onSave() {
    if (!model) return;
    try {
      await setLabels.mutateAsync({
        mid: model.id,
        labels: rows.filter((row) => row.label.trim()),
      });
      onClose();
    } catch {
      notifications.show({ message: "Failed to save labels", color: "red" });
    }
  }

  const used = new Set(rows.map((row) => row.label.trim().toLowerCase()));
  const suggestions = (labels ?? []).filter((label) => !used.has(label.name));

  return (
    <Modal opened={opened} onClose={onClose} title={model ? `Labels — ${model.name}` : "Labels"}>
      {rows.map((row, index) => (
        <Group key={index} align="end">
          <TextInput
            label="Label"
            value={row.label}
            onChange={(e) =>
              setRows((prev) =>
                prev.map((item, i) =>
                  i === index ? { ...item, label: e.currentTarget.value } : item,
                ),
              )
            }
          />
          <NumberInput
            label="Priority"
            value={row.priority}
            onChange={(value) =>
              setRows((prev) =>
                prev.map((item, i) =>
                  i === index ? { ...item, priority: Number(value) || 0 } : item,
                ),
              )
            }
          />
          <Button
            color="red"
            variant="subtle"
            onClick={() => setRows((prev) => prev.filter((_, i) => i !== index))}
          >
            Remove
          </Button>
        </Group>
      ))}
      <Button variant="light" onClick={() => setRows((prev) => [...prev, { label: "", priority: 0 }])}>
        Add label
      </Button>
      {suggestions.length > 0 && (
        <Group mt="sm">
          {suggestions.map((label) => (
            <Badge
              key={label.id}
              style={{ cursor: "pointer" }}
              onClick={() => setRows((prev) => [...prev, { label: label.name, priority: 0 }])}
            >
              {label.name}
            </Badge>
          ))}
        </Group>
      )}
      <Button mt="md" onClick={onSave} loading={setLabels.isPending}>
        Save
      </Button>
    </Modal>
  );
}
```

In `ModelsTab`, add state and filtering:

```tsx
  const { data: labels } = useLabels();
  const [labelFilter, setLabelFilter] = useState<string | null>(null);
  const [editing, setEditing] = useState<Model | null>(null);
  const [labelsOpen, setLabelsOpen] = useState(false);

  const visibleModels = (models ?? []).filter(
    (model) => !labelFilter || model.labels.some((label) => label.name === labelFilter),
  );
```

Add a filter selector above the table:

```tsx
        <Select
          label="Filter by label"
          clearable
          data={(labels ?? []).map((label) => label.name)}
          value={labelFilter}
          onChange={setLabelFilter}
        />
```

Add a Labels column and the edit action, replace `(models ?? []).map(` with `visibleModels.map(` in the table body, and use:

```tsx
              <Table.Th>Labels</Table.Th>
              <Table.Th>Actions</Table.Th>
...
              <Table.Td>
                {m.labels.map((label) => (
                  <Badge key={label.id} mr={4}>
                    {label.name}
                  </Badge>
                ))}
              </Table.Td>
              <Table.Td>
                <Button
                  size="xs"
                  variant="light"
                  mr={4}
                  onClick={() => {
                    setEditing(m);
                    setLabelsOpen(true);
                  }}
                >
                  Edit labels
                </Button>
                <Button size="xs" color="red" onClick={() => del.mutateAsync(m.id)}>
                  Delete
                </Button>
              </Table.Td>
```

Render `<ModelLabelsModal model={editing} opened={labelsOpen} onClose={() => setLabelsOpen(false)} />` inside the tab.

- [ ] **Step 2: Typecheck**

Run: `bun run build` (workdir `apps/web`)
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/pages/ProvidersPage.tsx
git commit -m "feat(web): model labels column, filter, and editor"
```

---

### Task 7: Agents form label selector + E2E

**Files:**
- Modify: `apps/web/src/pages/AgentsPage.tsx`
- Modify: `apps/web/e2e/provider-model-admin.spec.ts`

**Interfaces:**
- Consumes: `useLabels`, `useProviders`, `AgentSpec.model_binding.model`, `AgentSpec.model_label`.

- [ ] **Step 1: Update the Agents form**

In `AgentsPage.tsx`, import `useLabels`, `useProviders`. Replace the `model` state with a composite reference:

```tsx
  const { data: labels } = useLabels();
  const { data: providers } = useProviders();
  const [modelRef, setModelRef] = useState<string | null>(null);

  const providerName = (id: string) =>
    providers?.find((provider) => provider.id === id)?.name ?? id;
  const modelOptions = [
    ...(models ?? []).map((model) => ({
      value: `model:${model.id}`,
      label: `${providerName(model.provider_id)} · ${model.name}`,
    })),
    ...(labels ?? []).map((label) => ({
      value: `label:${label.name}`,
      label: `label: ${label.name}`,
    })),
  ];
```

In `onCreate`:

```tsx
    if (!modelRef) return;
    const isLabel = modelRef.startsWith("label:");
    const modelName = isLabel
      ? undefined
      : models?.find((model) => `model:${model.id}` === modelRef)?.name;
    ...
      await create.mutateAsync({
        name,
        ...
        model: modelName,
        model_label: isLabel ? modelRef.slice("label:".length) : undefined,
        ...
      });
    ...
    setModelRef(null);
```

Replace the Select with:

```tsx
        <Select
          label="Model"
          data={modelOptions}
          value={modelRef}
          onChange={setModelRef}
          searchable
        />
```

In the table, add `<Table.Th>Model</Table.Th>` and `<Table.Th>Label</Table.Th>` headers and show the resolved model and label badge:

```tsx
              <Table.Td>{a.model_binding.model}</Table.Td>
              <Table.Td>{a.model_label ? <Badge>{a.model_label}</Badge> : null}</Table.Td>
```

Add a “Model” table header and import `Badge` from Mantine.

- [ ] **Step 2: Extend the E2E**

In `provider-model-admin.spec.ts`, add a `labelModel` and `labelAgent` name near the other names:

```ts
  const labelModel = `e2e-labelled-${suffix}`;
  const labelAgent = `e2e-label-ag-${suffix}`;
```

After the existing model create/delete block (the `extraModel` assertions), insert:

```ts
  await page.getByLabel("Model name").fill(labelModel);
  await page.getByRole("button", { name: "Create model" }).click();
  const labelledRow = page.getByRole("row", { name: new RegExp(labelModel) });
  await expect(labelledRow).toBeVisible();

  await labelledRow.getByRole("button", { name: "Edit labels" }).click();
  const labelsDialog = page.getByRole("dialog");
  await labelsDialog.getByRole("button", { name: "Add label" }).click();
  await labelsDialog.getByLabel("Label", { exact: true }).fill("fast");
  await labelsDialog.getByRole("button", { name: "Save" }).click();
  await expect(labelledRow.getByText("fast")).toBeVisible();

  await page.getByRole("combobox", { name: "Filter by label" }).click();
  await page.getByRole("option", { name: "fast" }).click();
  await expect(labelledRow).toBeVisible();

  await page.getByRole("link", { name: "Agents" }).click();
  await page.getByLabel("Name").fill(labelAgent);
  await page.getByRole("combobox", { name: "Model" }).click();
  await page.getByRole("option", { name: "label: fast" }).click();
  await page.getByRole("button", { name: "Create agent" }).click();
  const labelAgentRow = page.getByRole("row", { name: new RegExp(labelAgent) });
  await expect(labelAgentRow.getByText("fast")).toBeVisible();
```

- [ ] **Step 3: Run the focused E2E**

```bash
cd apps/web && bun run e2e -- provider-model-admin.spec.ts
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/pages/AgentsPage.tsx apps/web/e2e/provider-model-admin.spec.ts
git commit -m "feat(web): label-bound agent selection"
```

---

### Task 8: Roadmap and full verification

**Files:**
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Update the roadmap**

Remove the D7 row from the deferred backlog table and add:

```markdown
| 22 | Model labels + label-based model routing | `specs/2026-11-19-model-labels-design.md` | `plans/2026-11-19-model-labels.md` |
```

after sub-project #21.

- [ ] **Step 2: Full verification**

```bash
uv run ruff check --fix packages
uv run ty check packages
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-api -q
cd apps/web && bun run test && bun run build
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs(roadmap): model labels complete"
```
