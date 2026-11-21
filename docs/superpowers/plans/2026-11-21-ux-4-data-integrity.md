# UX-4 Data Integrity, Errors, and Navigation States Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Agentbox reject invalid data consistently and recover from failed reads, missing routes/sessions, destructive actions, and provider logging failures without misleading empty or broken states.

**Architecture:** Add one typed frontend API-error boundary and reusable error/confirmation primitives, then adopt them across pages. Add backend Pydantic/path validation, persisted session titles, and a traceback-string logging helper.

**Tech Stack:** React 19, TypeScript, Vite 8, Mantine 9, TanStack Query, RemixIcon, FastAPI, Pydantic, SQLModel, Alembic, loguru, Playwright, Vitest, Storybook 10.6.8.

## Global Constraints

- Do not add duplicate-name restrictions.
- Do not add undo or soft-delete workflows.
- Do not redesign active navigation; add only a regression check.
- Do not add LLM-generated titles.
- Trim and reject blank names; duplicate names remain allowed.
- Project paths may be relative but must resolve to an existing directory; extra roots must be absolute existing directories.
- Auto-title uses the first user prompt, max 60 characters (`57 + "..."` when truncated).
- Manual session titles are max 120 characters and never overwritten by auto-title.
- High-tier type-to-confirm: projects, agents, providers, users, roles, permissions.
- Standard confirm: sessions, models, API key revoke, agent card removal.
- Read failures never render a successful empty state.
- Log traceback text, never arbitrary exception objects, through loguru.
- Keep `pytest-timeout` settings unchanged; run one backend package per pytest invocation.
- Use Bun for frontend commands and `uv` for Python commands.

---

### Task 1: Safe exception logging

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/logging.py`
- Create: `packages/agentbox-harness/tests/test_logging.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/run.py`
- Modify: `packages/agentbox-api/src/agentbox_api/mcp_relay.py`

**Interfaces:**
- Consumes: loguru’s existing logger.
- Produces: `log_exception(message: str, *args: object) -> None`; logs the active traceback as text and never passes an exception object.

- [ ] **Step 1: Write the failing test**

```python
# packages/agentbox-harness/tests/test_logging.py
import pathlib

import pytest

from agentbox_harness.logging import log_exception
from loguru import logger


class UnpicklableError(Exception):
    def __reduce__(self):
        raise TypeError("cannot pickle this exception")


@pytest.mark.asyncio
async def test_log_exception_uses_text_for_unpicklable_exception(tmp_path: pathlib.Path):
    sink = tmp_path / "safe.log"
    sink_id = logger.add(sink, enqueue=True, format="{message}")
    try:
        try:
            raise UnpicklableError("auth failed")
        except UnpicklableError:
            log_exception("run failed id={}", "r1")
        await logger.complete()
    finally:
        logger.remove(sink_id)
    text = sink.read_text(encoding="utf-8")
    assert "run failed id=r1" in text
    assert "UnpicklableError: auth failed" in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
uv run pytest packages/agentbox-harness/tests/test_logging.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agentbox_harness.logging'`.

- [ ] **Step 3: Implement the helper**

```python
# packages/agentbox-harness/src/agentbox_harness/logging.py
import traceback

from loguru import logger


def log_exception(message: str, *args: object) -> None:
    """Log the active exception as traceback text, safe for enqueued sinks."""
    traceback_text = traceback.format_exc()
    logger.opt(exception=None).error("{} | {}", message.format(*args), traceback_text)
```

Replace every `logger.exception("...", run_id)` in `run.py` with `log_exception("...", run_id)` and add:

```python
from agentbox_harness.logging import log_exception
```

Replace the two `logger.exception` calls in `mcp_relay.py` the same way.

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```powershell
uv run pytest packages/agentbox-harness/tests/test_logging.py -q
uv run pytest packages/agentbox-api/tests/test_mcp_relay.py -q
```

Expected: both pass.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-harness/src/agentbox_harness/logging.py packages/agentbox-harness/src/agentbox_harness/run.py packages/agentbox-harness/tests/test_logging.py packages/agentbox-api/src/agentbox_api/mcp_relay.py
git commit -m "fix(harness): log exceptions as safe traceback text"
```

---

### Task 2: Backend validation helpers and route validators

**Files:**
- Create: `packages/agentbox-api/src/agentbox_api/validation.py`
- Create: `packages/agentbox-api/tests/test_validation.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/projects.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/providers.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/agents.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/permissions.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/roles.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/users.py`

**Interfaces:**
- Consumes: Pydantic `field_validator`.
- Produces: `required_name`, `checked_directory`, `checked_extra_roots`, `optional_http_url`.

- [ ] **Step 1: Write the failing API tests**

Use the existing in-memory app pattern from `test_management.py`.

```python
# packages/agentbox-api/tests/test_validation.py
import pathlib

import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import Permission, Role, RolePermissionLink, User, UserRoleLink


async def _make_app(perms: list[str]):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw")))
        s.add(Role(id="r1", name="admin"))
        for i, perm in enumerate(perms):
            s.add(Permission(id=f"p{i}", name=perm))
            s.add(RolePermissionLink(role_id="r1", permission_id=f"p{i}"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        await s.commit()
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    token = (await client.post("/auth/login", json={"username": "alice", "password": "pw"})).json()["access_token"]
    return engine, client, {"Authorization": f"Bearer {token}"}


async def test_project_name_and_path_validation(tmp_path: pathlib.Path, monkeypatch):
    engine, client, headers = await _make_app(["projects:create"])
    try:
        response = await client.post(
            "/projects", json={"name": "   ", "path": str(tmp_path)}, headers=headers
        )
        assert response.status_code == 422

        response = await client.post(
            "/projects", json={"name": "P", "path": str(tmp_path / "missing")}, headers=headers
        )
        assert response.status_code == 422

        file_path = tmp_path / "file.txt"
        file_path.write_text("x", encoding="utf-8")
        response = await client.post(
            "/projects", json={"name": "P", "path": str(file_path)}, headers=headers
        )
        assert response.status_code == 422

        monkeypatch.chdir(tmp_path)
        response = await client.post(
            "/projects", json={"name": " P ", "path": "."}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["name"] == "P"
    finally:
        await client.aclose()
        await engine.dispose()


async def test_extra_roots_must_be_absolute_directories(tmp_path: pathlib.Path):
    engine, client, headers = await _make_app(["projects:create"])
    try:
        response = await client.post(
            "/projects",
            json={"name": "P", "path": str(tmp_path), "extra_roots": ["relative"]},
            headers=headers,
        )
        assert response.status_code == 422

        response = await client.post(
            "/projects",
            json={"name": "P", "path": str(tmp_path), "extra_roots": [str(tmp_path / "missing")]},
            headers=headers,
        )
        assert response.status_code == 422
    finally:
        await client.aclose()
        await engine.dispose()


async def test_blank_resource_names_are_rejected(tmp_path: pathlib.Path):
    engine, client, headers = await _make_app(
        ["providers:create", "agents:create", "roles:manage", "users:manage"]
    )
    try:
        assert (
            await client.post(
                "/providers", json={"name": " ", "kind": "generic"}, headers=headers
            )
        ).status_code == 422
        assert (
            await client.post(
                "/agents", json={"name": " ", "model": "m"}, headers=headers
            )
        ).status_code == 422
        assert (
            await client.post(
                "/roles", json={"name": "   "}, headers=headers
            )
        ).status_code == 422
        assert (
            await client.post(
                "/users", json={"username": " ", "email": "a@x", "password": "pw"}, headers=headers
            )
        ).status_code == 422
    finally:
        await client.aclose()
        await engine.dispose()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
uv run pytest packages/agentbox-api/tests/test_validation.py -q
```

Expected: FAIL because blank names and invalid paths are accepted.

- [ ] **Step 3: Implement the validation helpers**

```python
# packages/agentbox-api/src/agentbox_api/validation.py
from pathlib import Path
from urllib.parse import urlparse


def required_name(value: str, field: str = "name") -> str:
    text = value.strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def checked_directory(value: str, field: str = "path") -> str:
    text = value.strip()
    if not text:
        raise ValueError(f"{field} is required")
    if not Path(text).expanduser().resolve().is_dir():
        raise ValueError(f"{field} must be an existing directory")
    return text


def checked_extra_roots(values: list[str]) -> list[str]:
    roots: list[str] = []
    for value in values:
        text = value.strip()
        path = Path(text).expanduser()
        if not text or not path.is_absolute() or not path.resolve().is_dir():
            raise ValueError("Each additional folder must be an absolute existing directory")
        roots.append(text)
    return roots


def optional_http_url(value: str | None, field: str) -> str | None:
    if value is None or value == "":
        return value
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"{field} must be an http/https URL")
    return value
```

Apply validators:

```python
# projects.py
from pydantic import field_validator
from agentbox_api.validation import checked_directory, checked_extra_roots, required_name


class ProjectCreate(BaseModel):
    name: str
    path: str
    extra_roots: list[str] = []

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return required_name(value)

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        return checked_directory(value)

    @field_validator("extra_roots")
    @classmethod
    def _roots(cls, value: list[str]) -> list[str]:
        return checked_extra_roots(value)


class ProjectUpdate(BaseModel):
    name: str | None = None
    extra_roots: list[str] | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return required_name(value) if value is not None else None

    @field_validator("extra_roots")
    @classmethod
    def _roots(cls, value: list[str] | None) -> list[str] | None:
        return checked_extra_roots(value) if value is not None else None
```

Add equivalent `@field_validator("name")` methods using `required_name` to `ProviderCreate`, `ProviderUpdate`, `AgentCreate`, `RoleCreate`, `RoleUpdate`, `PermissionCreate`, `PermissionUpdate`, and `UserCreate` (use field names `username`, `email`, `password` for `UserCreate`). Add `base_url` and `models_url` validators using `optional_http_url`.

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```powershell
uv run pytest packages/agentbox-api/tests/test_validation.py -q
uv run pytest packages/agentbox-api/tests/test_management.py -q
uv run pytest packages/agentbox-api/tests/test_admin_routers.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-api/src/agentbox_api/validation.py packages/agentbox-api/src/agentbox_api/routers packages/agentbox-api/tests/test_validation.py
git commit -m "fix(api): validate required names and project paths"
```

---

### Task 3: Session titles and title API

**Files:**
- Modify: `packages/agentbox-models/src/agentbox_models/tables/core.py`
- Create: `packages/agentbox-models/alembic/versions/e5f6a7b8c9d0_session_title.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`
- Create: `packages/agentbox-api/tests/test_session_title.py`
- Generated: `apps/web/openapi.json`
- Generated: `apps/web/src/api/schema.d.ts`

**Interfaces:**
- Consumes: existing session creation and chat flow.
- Produces: `SessionRow.title`, `SessionDetail.title`, `PATCH /sessions/{sid}`, `derive_session_title(content: str) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# packages/agentbox-api/tests/test_session_title.py
import pathlib

import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.routers.sessions import derive_session_title
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import Permission, Role, RolePermissionLink, User, UserRoleLink
from agentbox_models.tables.core import Agent, Model, Project, Provider, SessionRow


def test_derive_session_title_normalizes_and_truncates():
    assert derive_session_title("  hello \n world  ") == "hello world"
    title = derive_session_title("x" * 80)
    assert len(title) == 60
    assert title.endswith("...")


async def _seed(factory, tmp_path: pathlib.Path):
    async with factory() as s:
        s.add(Provider(id="p", name="test", kind="generic", base_url="http://localhost:1"))
        s.add(Model(id="m", provider_id="p", name="test-model"))
        s.add(Agent(id="a", name="bot", description="", instructions="", model_id="m"))
        s.add(Project(id="prj", name="proj", path=str(tmp_path), owner_id="u1"))
        s.add(SessionRow(id="s1", project_id="prj", agent_id="a"))
        s.add(User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw")))
        s.add(Role(id="r1", name="role"))
        s.add(Permission(id="perm1", name="sessions:create"))
        s.add(Permission(id="perm2", name="sessions:read"))
        s.add(RolePermissionLink(role_id="r1", permission_id="perm1"))
        s.add(RolePermissionLink(role_id="r1", permission_id="perm2"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        await s.commit()


async def _login(client):
    token = (await client.post("/auth/login", json={"username": "alice", "password": "pw"})).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_rename_session_and_reject_blank(tmp_path: pathlib.Path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    await _seed(factory, tmp_path)
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        headers = await _login(client)
        response = await client.patch("/sessions/s1", json={"title": " Release plan "}, headers=headers)
        assert response.status_code == 200
        assert response.json()["title"] == "Release plan"

        response = await client.patch("/sessions/s1", json={"title": "   "}, headers=headers)
        assert response.status_code == 422
    finally:
        await client.aclose()
        await engine.dispose()


async def test_first_message_sets_title_once(tmp_path: pathlib.Path, monkeypatch):
    from pydantic_ai.models.test import TestModel

    monkeypatch.setattr(
        "agentbox_api.runtime.resolve_model",
        lambda provider, name, context_window=None: TestModel(call_tools=[]),
    )
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    await _seed(factory, tmp_path)
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        headers = await _login(client)
        async with client.stream(
            "POST", "/sessions/s1/messages", json={"content": "Plan the release"}, headers=headers
        ) as response:
            _ = [chunk async for chunk in response.aiter_text()]
        async with factory() as session:
            row = await session.get(SessionRow, "s1")
            assert row is not None
            assert row.title == "Plan the release"
    finally:
        await client.aclose()
        await engine.dispose()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
uv run pytest packages/agentbox-api/tests/test_session_title.py -q
```

Expected: FAIL because `title` and `derive_session_title` do not exist.

- [ ] **Step 3: Implement the model, migration, and route**

Add to `SessionRow`:

```python
title: str | None = None
```

Create the migration:

```python
# packages/agentbox-models/alembic/versions/e5f6a7b8c9d0_session_title.py
"""session title

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-21 18:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sessionrow") as batch:
        batch.add_column(sa.Column("title", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sessionrow") as batch:
        batch.drop_column("title")
```

Add to `sessions.py`:

```python
class SessionTitleUpdate(BaseModel):
    title: str

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        text = " ".join(value.split())
        if not text:
            raise ValueError("title is required")
        if len(text) > 120:
            raise ValueError("title must be 120 characters or fewer")
        return text


def derive_session_title(content: str) -> str:
    text = " ".join(content.split())
    return text if len(text) <= 60 else text[:57] + "..."


@router.patch("/{sid}", response_model=SessionRow)
async def rename_session(
    sid: str,
    body: SessionTitleUpdate,
    request: Request,
    _=Depends(require_permission("sessions:create")),
):
    async with request.app.state.session_factory() as s:
        row = await s.get(SessionRow, sid)
        if row is None:
            raise HTTPException(status_code=404, detail="Not found")
        row.title = body.title
        s.add(row)
        await s.commit()
        await s.refresh(row)
    return row
```

Add `title=row.title` to `SessionDetail` and the response constructor.

In `chat`, after retry/body content resolution and before `harness.run`, persist an initial title:

```python
if not srow.title:
    initial_title = derive_session_title(body.content)
    async with factory() as s:
        title_row = await s.get(SessionRow, sid)
        if title_row is not None and not title_row.title:
            title_row.title = initial_title
            s.add(title_row)
            await s.commit()
            srow.title = initial_title
```

Add `from pydantic import BaseModel, field_validator` to the imports.

- [ ] **Step 4: Run the tests and regenerate the API artifacts**

Run:

```powershell
uv run pytest packages/agentbox-api/tests/test_session_title.py -q
uv run pytest packages/agentbox-models -q
uv run python apps/web/scripts/gen-openapi.py
```

Then:

```powershell
cd apps/web
bun run codegen
```

Expected: tests pass and generated schema includes `title`.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-models packages/agentbox-api/src/agentbox_api/routers/sessions.py packages/agentbox-api/tests/test_session_title.py apps/web/openapi.json apps/web/src/api/schema.d.ts
git commit -m "feat(sessions): add automatic and editable titles"
```

---

### Task 4: Typed frontend API errors and retry policy

**Files:**
- Create: `apps/web/src/api/errors.ts`
- Create: `apps/web/src/api/errors.test.ts`
- Create: `apps/web/src/api/queryClient.ts`
- Create: `apps/web/src/api/queryClient.test.ts`
- Modify: `apps/web/src/api/endpoints.ts`
- Modify: `apps/web/src/App.tsx`

**Interfaces:**
- Consumes: `openapi-fetch` responses.
- Produces: `ApiError`, `toApiError(error, fallback, status?)`, `createQueryClient()`, `shouldRetry(failureCount, error)`.

- [ ] **Step 1: Write the failing tests**

```ts
// apps/web/src/api/errors.test.ts
import { ApiError, toApiError } from "./errors";

test("normalizes a string detail", () => {
  const error = toApiError({ detail: "Session not found" }, "fallback", 404);
  expect(error).toBeInstanceOf(ApiError);
  expect(error.status).toBe(404);
  expect(error.detail).toBe("Session not found");
});

test("normalizes validation arrays into fields", () => {
  const error = toApiError(
    {
      detail: [
        { loc: ["body", "name"], msg: "name is required" },
        { loc: ["body", "path"], msg: "path must be a directory" },
      ],
    },
    "fallback",
    422,
  );
  expect(error.fields).toEqual({
    name: "name is required",
    path: "path must be a directory",
  });
});

test("normalizes network failures", () => {
  const error = toApiError(new TypeError("fetch failed"), "Network unavailable");
  expect(error.status).toBe(0);
  expect(error.detail).toBe("Network unavailable");
});
```

```ts
// apps/web/src/api/queryClient.test.ts
import { ApiError } from "./errors";
import { shouldRetry } from "./queryClient";

test("retries 5xx once and never retries 4xx", () => {
  expect(shouldRetry(0, new ApiError("boom", 500))).toBe(true);
  expect(shouldRetry(1, new ApiError("boom", 500))).toBe(false);
  expect(shouldRetry(0, new ApiError("missing", 404))).toBe(false);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
cd apps/web
bun run test -- src/api/errors.test.ts src/api/queryClient.test.ts
```

Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement errors and query client**

```ts
// apps/web/src/api/errors.ts
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public fields?: Record<string, string>,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function detailText(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) =>
        item && typeof item === "object" && "msg" in item
          ? String((item as { msg: unknown }).msg)
          : "",
      )
      .filter(Boolean);
    return messages.length > 0 ? messages.join("; ") : null;
  }
  return null;
}

function fieldMap(detail: unknown): Record<string, string> | undefined {
  if (!Array.isArray(detail)) return undefined;
  const fields: Record<string, string> = {};
  for (const item of detail) {
    if (!item || typeof item !== "object") continue;
    const loc = (item as { loc?: unknown }).loc;
    const msg = (item as { msg?: unknown }).msg;
    if (!Array.isArray(loc) || typeof msg !== "string") continue;
    const key = [...loc].reverse().find((part) => typeof part === "string");
    if (typeof key === "string") fields[key] = msg;
  }
  return Object.keys(fields).length > 0 ? fields : undefined;
}

export function toApiError(
  error: unknown,
  fallback: string,
  status = 0,
): ApiError {
  const detail =
    error && typeof error === "object" && "detail" in error
      ? (error as { detail?: unknown }).detail
      : undefined;
  return new ApiError(detailText(detail) ?? fallback, status, fieldMap(detail));
}
```

```ts
// apps/web/src/api/queryClient.ts
import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./errors";

export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= 1) return false;
  if (!(error instanceof ApiError)) return true;
  return error.status === 0 || error.status >= 500;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: shouldRetry } } });
}
```

Update `App.tsx`:

```ts
import { createQueryClient } from "./api/queryClient";
const queryClient = createQueryClient();
```

Update every request helper in `endpoints.ts` to throw `toApiError(error, fallback, response.status)` and return successful data. Example:

```ts
export async function fetchProjects(): Promise<Project[]> {
  const { data, error, response } = await api.GET("/projects");
  if (error) throw toApiError(error, "Failed to load projects", response.status);
  return data ?? [];
}
```

Apply the same error handling to all `fetch*`, `create*`, `update*`, `delete*`, `set*`, `save*`, `upload*`, and `revoke*` helpers. Keep `fetchAgentCard` returning `null` on 404, but throw for other non-404 responses:

```ts
export async function fetchAgentCard(name: string): Promise<AgentCard | null> {
  const { data, error, response } = await api.GET("/agents/{name}/card", {
    params: { path: { name } },
  });
  if (response.status === 404) return null;
  if (error) throw toApiError(error, "Failed to load agent card", response.status);
  return (data as AgentCard) ?? null;
}
```

- [ ] **Step 4: Run the tests and typecheck**

Run:

```powershell
cd apps/web
bun run test -- src/api/errors.test.ts src/api/queryClient.test.ts
bun run build
```

Expected: tests pass and `tsc` is clean.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/api/errors.ts apps/web/src/api/errors.test.ts apps/web/src/api/queryClient.ts apps/web/src/api/queryClient.test.ts apps/web/src/api/endpoints.ts apps/web/src/App.tsx
git commit -m "fix(web): normalize API errors and retries"
```

---

### Task 5: Shared error, 404, and session-not-found states

**Files:**
- Create: `apps/web/src/design-system/patterns/ErrorState.tsx`
- Create: `apps/web/src/design-system/patterns/ErrorState.test.tsx`
- Create: `apps/web/src/pages/NotFoundPage.tsx`
- Create: `apps/web/src/pages/NotFoundPage.test.tsx`
- Create: `apps/web/src/pages/session/SessionNotFound.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/api/queries.ts`
- Modify: `apps/web/src/pages/SessionPage.tsx`
- Create: `apps/web/src/pages/SessionPage.ux4.test.tsx`

**Interfaces:**
- Consumes: `ApiError`.
- Produces: `ErrorState`, `NotFoundPage`, `SessionNotFound`; `useMessages(sessionId, enabled?)`, `useSessionLsp(sessionId, enabled?)`, `useSessionPlan(sessionId, running?, enabled?)`.

- [ ] **Step 1: Write the failing UI tests**

```tsx
// apps/web/src/design-system/patterns/ErrorState.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { ThemeProvider } from "../theme/ThemeProvider";
import { ErrorState } from "./ErrorState";

test("shows the message and invokes retry", () => {
  const retry = vi.fn();
  render(
    <ThemeProvider forceScheme="dark">
      <ErrorState title="Could not load providers" message="Server exploded" onRetry={retry} />
    </ThemeProvider>,
  );
  expect(screen.getByText("Server exploded")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(retry).toHaveBeenCalled();
});
```

```tsx
// apps/web/src/pages/NotFoundPage.test.tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { ThemeProvider } from "../design-system/theme/ThemeProvider";
import { NotFoundPage } from "./NotFoundPage";

test("renders a usable 404 page", () => {
  render(
    <ThemeProvider forceScheme="dark">
      <MemoryRouter>
        <NotFoundPage />
      </MemoryRouter>
    </ThemeProvider>,
  );
  expect(screen.getByRole("heading", { name: /page not found/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /back to home/i })).toBeInTheDocument();
});
```

Add `SessionPage.ux4.test.tsx` that mocks `useSession` to return an `ApiError("Not found", 404)` and asserts “Session not found” plus absence of the Message composer.

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
cd apps/web
bun run test -- src/design-system/patterns/ErrorState.test.tsx src/pages/NotFoundPage.test.tsx src/pages/SessionPage.ux4.test.tsx
```

Expected: FAIL because the components do not exist.

- [ ] **Step 3: Implement the shared states and session gate**

Create `ErrorState.tsx`:

```tsx
import { RiErrorWarningLine } from "@remixicon/react";

import { Button } from "../primitives/Button";
import { Icon } from "../icons/Icon";
import { Panel } from "../primitives/Panel";

export function ErrorState({
  title = "Could not load data",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry: () => void;
}) {
  return (
    <Panel>
      <Panel.Body>
        <div style={{ display: "grid", gap: 10, justifyItems: "start" }}>
          <Icon as={RiErrorWarningLine} size={28} />
          <h2>{title}</h2>
          <p>{message}</p>
          <Button onClick={onRetry}>Retry</Button>
        </div>
      </Panel.Body>
    </Panel>
  );
}
```

Create `NotFoundPage.tsx` using `PageContainer`, `PageHeader`, `ErrorState`-style content, and `useNavigate`:

```tsx
export function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <PageContainer>
      <PageHeader title="404 — Page not found" subtitle="That route does not exist." />
      <Panel>
        <Panel.Body>
          <Button onClick={() => navigate("/")}>Back to Home</Button>
        </Panel.Body>
      </Panel>
    </PageContainer>
  );
}
```

Create `SessionNotFound.tsx` with “Back to Home” and “Browse projects” buttons. “Browse projects” navigates to `/`.

Add to `App.tsx` inside the authenticated shell:

```tsx
<Route path="*" element={<NotFoundPage />} />
```

Change query signatures:

```ts
export function useMessages(sessionId: string, enabled = true) {
  return useQuery({
    queryKey: ["messages", sessionId],
    queryFn: () => fetchMessages(sessionId),
    enabled: enabled && !!sessionId,
  });
}

export function useSessionLsp(sessionId: string, enabled = true) {
  return useQuery({
    queryKey: ["session-lsp", sessionId],
    queryFn: () => fetchSessionLsp(sessionId),
    enabled: enabled && !!sessionId,
  });
}

export function useSessionPlan(sessionId: string, running = false, enabled = true) {
  return useQuery({
    queryKey: ["session-plan", sessionId],
    queryFn: () => fetchSessionPlan(sessionId),
    enabled: enabled && !!sessionId,
    refetchInterval: running ? 2000 : false,
  });
}
```

In `SessionPage`, derive:

```ts
const sessionQuery = useSession(id);
const notFound =
  sessionQuery.error instanceof ApiError && sessionQuery.error.status === 404;
const sessionEnabled = !notFound;
const { data: session } = sessionQuery;
const { data: messages } = useMessages(id, sessionEnabled);
const { data: lsp } = useSessionLsp(id, sessionEnabled);
const { data: plan } = useSessionPlan(id, chat.running, sessionEnabled);
```

Before the normal return:

```tsx
if (notFound) return <SessionNotFound />;
if (sessionQuery.error) {
  return (
    <PageContainer>
      <ErrorState
        title="Could not load session"
        message={sessionQuery.error.message}
        onRetry={() => void sessionQuery.refetch()}
      />
    </PageContainer>
  );
}
```

- [ ] **Step 4: Run the tests**

Run:

```powershell
cd apps/web
bun run test -- src/design-system/patterns/ErrorState.test.tsx src/pages/NotFoundPage.test.tsx src/pages/SessionPage.ux4.test.tsx
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/design-system/patterns/ErrorState.tsx apps/web/src/design-system/patterns/ErrorState.test.tsx apps/web/src/pages/NotFoundPage.tsx apps/web/src/pages/NotFoundPage.test.tsx apps/web/src/pages/session/SessionNotFound.tsx apps/web/src/App.tsx apps/web/src/api/queries.ts apps/web/src/pages/SessionPage.tsx apps/web/src/pages/SessionPage.ux4.test.tsx
git commit -m "feat(web): add error and not-found states"
```

---

### Task 6: Validation helpers and project/session forms

**Files:**
- Create: `apps/web/src/lib/validation.ts`
- Create: `apps/web/src/lib/validation.test.ts`
- Modify: `apps/web/src/components/projects/NewProjectModal.tsx`
- Modify: `apps/web/src/components/projects/NewSessionModal.tsx`
- Modify: `apps/web/src/design-system/navigation/ProjectPanel.test.tsx`

**Interfaces:**
- Produces: `requiredText`, `isHttpUrl`, `isAbsolutePath`.

- [ ] **Step 1: Write failing tests**

```ts
// apps/web/src/lib/validation.test.ts
import { isAbsolutePath, requiredText } from "./validation";

test("requiredText trims and rejects blanks", () => {
  expect(requiredText("  hello ", "Name")).toBeNull();
  expect(requiredText("   ", "Name")).toBe("Name is required.");
});

test("isAbsolutePath accepts POSIX, drive, and UNC paths", () => {
  expect(isAbsolutePath("/tmp")).toBe(true);
  expect(isAbsolutePath("C:\\tmp")).toBe(true);
  expect(isAbsolutePath("\\\\server\\share")).toBe(true);
  expect(isAbsolutePath("relative/path")).toBe(false);
});
```

Add a `ProjectPanel.test.tsx` case that submits a blank project name and asserts “Name is required.” with no `createProject` call.

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
cd apps/web
bun run test -- src/lib/validation.test.ts src/design-system/navigation/ProjectPanel.test.tsx
```

Expected: FAIL.

- [ ] **Step 3: Implement validation and update forms**

```ts
// apps/web/src/lib/validation.ts
export function requiredText(value: string, label: string): string | null {
  return value.trim() ? null : `${label} is required.`;
}

export function isHttpUrl(value: string, label = "URL"): string | null {
  const text = value.trim();
  if (!text) return null;
  try {
    const url = new URL(text);
    return url.protocol === "http:" || url.protocol === "https:"
      ? null
      : `${label} must use http or https.`;
  } catch {
    return `${label} must be a valid URL.`;
  }
}

export function isAbsolutePath(value: string): boolean {
  const text = value.trim();
  return text.startsWith("/") || /^[A-Za-z]:[\\/]/.test(text) || text.startsWith("\\\\");
}
```

In `NewProjectModal`, use design-system `FormField` and `TextInput`, add local errors:

```tsx
const [errors, setErrors] = useState<Record<string, string>>({});

function validate() {
  const next: Record<string, string> = {};
  const nameError = requiredText(name, "Name");
  if (nameError) next.name = nameError;
  if (!editing) {
    const pathError = requiredText(path, "Path");
    if (pathError) next.path = pathError;
  }
  const rootsError = splitRoots(roots).find((root) => !isAbsolutePath(root));
  if (rootsError) next.roots = "Additional folders must be absolute paths.";
  setErrors(next);
  return Object.keys(next).length === 0;
}
```

Call `if (!validate()) return;` before mutations and clear errors when the modal opens.

In `NewSessionModal`, use `FormField` and show:

```tsx
{!agentName && <p role="alert">Choose an agent to create a session.</p>}
<Button disabled={!agentName} ...>
```

Also guard `submit()` with `if (!agentName) return;`.

- [ ] **Step 4: Run the tests**

Run:

```powershell
cd apps/web
bun run test -- src/lib/validation.test.ts src/design-system/navigation/ProjectPanel.test.tsx
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/lib/validation.ts apps/web/src/lib/validation.test.ts apps/web/src/components/projects/NewProjectModal.tsx apps/web/src/components/projects/NewSessionModal.tsx apps/web/src/design-system/navigation/ProjectPanel.test.tsx
git commit -m "fix(web): validate project and session forms"
```

---

### Task 7: Provider, agent, and admin form validation

**Files:**
- Modify: `apps/web/src/pages/providers/providerPresets.ts`
- Modify: `apps/web/src/pages/providers/providerPresets.test.ts`
- Modify: `apps/web/src/pages/providers/ProviderForm.tsx`
- Modify: `apps/web/src/pages/ProvidersPage.tsx`
- Modify: `apps/web/src/onboarding/OnboardingWizard.tsx`
- Modify: `apps/web/src/pages/agents/AgentCreateDrawer.tsx`
- Modify: `apps/web/src/pages/AdminPage.tsx`

**Interfaces:**
- Consumes: `requiredText`, `isHttpUrl`.
- Produces: `validateProviderDraft(draft): Partial<Record<keyof ProviderDraft, string>>`.

- [ ] **Step 1: Write failing tests**

```ts
// apps/web/src/pages/providers/providerPresets.test.ts (add cases)
import { EMPTY_PROVIDER_DRAFT, validateProviderDraft } from "./providerPresets";

test("validator rejects a blank name and invalid URLs", () => {
  const errors = validateProviderDraft({
    ...EMPTY_PROVIDER_DRAFT,
    name: "  ",
    modelsUrl: "ftp://example.test/models",
  });
  expect(errors.name).toContain("required");
  expect(errors.modelsUrl).toContain("http");
});

test("validator accepts a named generic provider", () => {
  expect(
    validateProviderDraft({
      ...EMPTY_PROVIDER_DRAFT,
      name: "Local",
      modelsUrl: "http://localhost:9999/models",
    }),
  ).toEqual({});
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
cd apps/web
bun run test -- src/pages/providers/providerPresets.test.ts
```

Expected: FAIL because `validateProviderDraft` does not exist.

- [ ] **Step 3: Implement validation and wire forms**

Add to `providerPresets.ts`:

```ts
import { isHttpUrl, requiredText } from "../../lib/validation";

export function validateProviderDraft(
  draft: ProviderDraft,
): Partial<Record<keyof ProviderDraft, string>> {
  const errors: Partial<Record<keyof ProviderDraft, string>> = {};
  const name = requiredText(draft.name, "Name");
  if (name) errors.name = name;
  const base = isHttpUrl(draft.baseUrl, "Base URL");
  if (base) errors.baseUrl = base;
  const models = isHttpUrl(draft.modelsUrl, "Models URL");
  if (models) errors.modelsUrl = models;
  return errors;
}
```

Add to `ProviderForm` props:

```ts
errors?: Partial<Record<"name" | "kind" | "baseUrl" | "modelsUrl" | "apiKey", string>>;
```

Pass `error={errors?.name}` to the Name `FormField`, `error={errors?.baseUrl}` to Base URL, and `error={errors?.modelsUrl}` to Models URL.

In `ProvidersPage`, keep local `errors` and call `validateProviderDraft` in `onSave`; pass errors to `ProviderForm`.

In `OnboardingWizard`, run `validateProviderDraft` in `createProviderStep` and render a form-level error before calling the mutation.

In `AgentCreateDrawer`, add `errors` state and validate:

```ts
const next: Record<string, string> = {};
const nameError = requiredText(name, "Name");
if (nameError) next.name = nameError;
if (!modelRef) next.model = "Choose a model.";
setErrors(next);
if (Object.keys(next).length > 0) return;
```

Pass `error={errors.name}` to the Name `FormField` and `error={errors.model}` to Model.

In `AdminPage`, validate non-blank permission/role/user fields with `requiredText` before each create/save mutation and render `FormField` errors or a form-level `<p role="alert">`.

- [ ] **Step 4: Run the tests and build**

Run:

```powershell
cd apps/web
bun run test -- src/pages/providers/providerPresets.test.ts src/pages/agents/agentFormValidation.test.ts
bun run build
```

Expected: pass and typecheck.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/pages/providers/providerPresets.ts apps/web/src/pages/providers/providerPresets.test.ts apps/web/src/pages/providers/ProviderForm.tsx apps/web/src/pages/ProvidersPage.tsx apps/web/src/onboarding/OnboardingWizard.tsx apps/web/src/pages/agents/AgentCreateDrawer.tsx apps/web/src/pages/AdminPage.tsx
git commit -m "fix(web): validate provider, agent, and admin forms"
```

---

### Task 8: Tiered confirmation dialog

**Files:**
- Modify: `apps/web/src/design-system/overlays/ConfirmDialog.tsx`
- Modify: `apps/web/src/design-system/overlays/overlays.test.tsx`
- Modify: `apps/web/src/design-system/overlays/overlays.stories.tsx`

**Interfaces:**
- Produces: `ConfirmDialog` props `requireText?: string`, `onConfirm: () => Promise<void> | void` with internal pending/error state.

- [ ] **Step 1: Write failing tests**

```tsx
// add to overlays.test.tsx
test("type-to-confirm stays disabled until the exact name is entered", async () => {
  const onConfirm = vi.fn();
  render(
    <ThemeProvider forceScheme="dark">
      <ConfirmDialog
        opened
        title="Delete project?"
        description="This cannot be undone."
        requireText="Demo"
        confirmLabel="Delete"
        danger
        onConfirm={onConfirm}
        onClose={() => {}}
      />
    </ThemeProvider>,
  );
  const confirm = screen.getByRole("button", { name: "Delete" });
  expect(confirm).toBeDisabled();
  fireEvent.change(screen.getByLabelText(/type Demo/i), { target: { value: "Demo" } });
  expect(confirm).not.toBeDisabled();
  fireEvent.click(confirm);
  await waitFor(() => expect(onConfirm).toHaveBeenCalled());
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
cd apps/web
bun run test -- src/design-system/overlays/overlays.test.tsx
```

Expected: FAIL because `requireText` is unsupported.

- [ ] **Step 3: Implement the dialog**

```tsx
import { Button, Group, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";

import { Modal } from "./Modal";

export function ConfirmDialog({
  opened,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger,
  requireText,
  onConfirm,
  onClose,
}: {
  opened: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  requireText?: string;
  onConfirm: () => Promise<void> | void;
  onClose: () => void;
}) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (opened) {
      setTyped("");
      setError(null);
    }
  }, [opened]);

  const matches = !requireText || typed.trim() === requireText.trim();

  async function confirm() {
    if (!matches) return;
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal opened={opened} onClose={onClose} title={title}>
      <p>{description}</p>
      {requireText && (
        <TextInput
          label={`Type ${requireText} to confirm`}
          value={typed}
          onChange={(event) => setTyped(event.currentTarget.value)}
        />
      )}
      {error && <p role="alert">{error}</p>}
      <Group justify="flex-end" mt="md">
        <Button variant="light" onClick={onClose}>
          {cancelLabel}
        </Button>
        <Button
          color={danger ? "danger" : "phosphor"}
          disabled={!matches}
          loading={busy}
          onClick={confirm}
        >
          {confirmLabel}
        </Button>
      </Group>
    </Modal>
  );
}
```

- [ ] **Step 4: Run the tests**

Run:

```powershell
cd apps/web
bun run test -- src/design-system/overlays/overlays.test.tsx
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/design-system/overlays/ConfirmDialog.tsx apps/web/src/design-system/overlays/overlays.test.tsx apps/web/src/design-system/overlays/overlays.stories.tsx
git commit -m "feat(web): add tiered confirmation dialog"
```

---

### Task 9: High-tier destructive confirmations

**Files:**
- Modify: `apps/web/src/design-system/navigation/ProjectPanel.tsx`
- Modify: `apps/web/src/pages/agents/AgentList.tsx`
- Modify: `apps/web/src/pages/ProvidersPage.tsx`
- Modify: `apps/web/src/pages/AdminPage.tsx`
- Modify: `apps/web/src/design-system/navigation/ProjectPanel.test.tsx`

**Interfaces:**
- Consumes: `ConfirmDialog` with `requireText`.
- Produces: high-tier deletion flows for projects, agents, providers, users, roles, permissions.

- [ ] **Step 1: Write failing tests**

Update `ProjectPanel.test.tsx`:

```tsx
test("requires the project name before deleting", async () => {
  renderPanel();
  fireEvent.click(await screen.findByLabelText("Delete Proj A"));
  const confirm = screen.getByRole("button", { name: "Delete" });
  expect(confirm).toBeDisabled();
  fireEvent.change(screen.getByLabelText(/type Proj A/i), { target: { value: "Proj A" } });
  fireEvent.click(confirm);
  await waitFor(() => expect(deleteProjectMock).toHaveBeenCalledWith("p1"));
});
```

Add a `deleteProjectMock` similar to `deleteSessionMock`.

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
cd apps/web
bun run test -- src/design-system/navigation/ProjectPanel.test.tsx
```

Expected: FAIL because project deletion is immediate.

- [ ] **Step 3: Implement high-tier confirmations**

In `ProjectPanel`, replace `modals.openConfirmModal` and direct `deleteProject.mutate` with local state:

```tsx
const [projectToDelete, setProjectToDelete] = useState<Project | null>(null);
```

Render:

```tsx
<ConfirmDialog
  opened={projectToDelete !== null}
  title="Delete project?"
  description={`Delete "${projectToDelete?.name ?? ""}" permanently? This cannot be undone.`}
  requireText={projectToDelete?.name}
  confirmLabel="Delete project"
  danger
  onConfirm={async () => {
    if (!projectToDelete) return;
    await deleteProject.mutateAsync(projectToDelete.id);
    setProjectToDelete(null);
    if (location.pathname !== "/") navigate("/");
  }}
  onClose={() => setProjectToDelete(null)}
/>
```

Use the same pattern in:
- `AgentList`: `requireText={agent.name}`, `onConfirm={() => del.mutateAsync(agent.name)}`.
- `ProvidersPage`: `requireText={provider.name}`.
- `AdminPage` permissions/roles/users: `requireText={p.name}`, `requireText={r.name}`, `requireText={u.username}`.

All delete buttons should open the dialog instead of calling the mutation directly.

- [ ] **Step 4: Run the tests**

Run:

```powershell
cd apps/web
bun run test -- src/design-system/navigation/ProjectPanel.test.tsx
bun run build
```

Expected: pass and typecheck.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/design-system/navigation/ProjectPanel.tsx apps/web/src/pages/agents/AgentList.tsx apps/web/src/pages/ProvidersPage.tsx apps/web/src/pages/AdminPage.tsx apps/web/src/design-system/navigation/ProjectPanel.test.tsx
git commit -m "feat(web): require names for high-impact deletions"
```

---

### Task 10: Standard destructive confirmations

**Files:**
- Modify: `apps/web/src/design-system/navigation/ProjectPanel.tsx`
- Modify: `apps/web/src/pages/ProvidersPage.tsx`
- Modify: `apps/web/src/pages/ApiKeysPage.tsx`
- Modify: `apps/web/src/pages/agents/AgentCardModal.tsx`
- Modify: `apps/web/src/design-system/navigation/ProjectPanel.test.tsx`

**Interfaces:**
- Consumes: `ConfirmDialog`.
- Produces: standard confirmation for sessions, models, API keys, agent cards.

- [ ] **Step 1: Write failing tests**

In `ProjectPanel.test.tsx`, change the delete-session test:

```tsx
test("confirms before deleting a session", async () => {
  renderPanel();
  fireEvent.click(await screen.findByLabelText("Delete session s1"));
  fireEvent.click(screen.getByRole("button", { name: "Delete" }));
  await waitFor(() => expect(deleteSessionMock).toHaveBeenCalledWith("s1"));
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
cd apps/web
bun run test -- src/design-system/navigation/ProjectPanel.test.tsx
```

Expected: FAIL because the old Mantine confirm is gone or the button label differs.

- [ ] **Step 3: Implement standard confirmations**

- `ProjectPanel`: replace `modals.openConfirmModal` for sessions with local `sessionToDelete` state and `ConfirmDialog` (no `requireText`).
- `ProvidersPage`: add `modelToDelete` state and standard `ConfirmDialog` for model deletion.
- `ApiKeysPage`: add `keyToRevoke` state and standard `ConfirmDialog` for `Revoke`.
- `AgentCardModal`: add `confirmRemove` state and standard `ConfirmDialog` for “Remove” before calling `remove.mutateAsync`.

Example for API keys:

```tsx
<ConfirmDialog
  opened={keyToRevoke !== null}
  title="Revoke API key?"
  description="This key will stop working immediately. This cannot be undone."
  confirmLabel="Revoke key"
  danger
  onConfirm={async () => {
    if (!keyToRevoke) return;
    await revoke.mutateAsync(keyToRevoke.id);
    setKeyToRevoke(null);
  }}
  onClose={() => setKeyToRevoke(null)}
/>
```

- [ ] **Step 4: Run the tests**

Run:

```powershell
cd apps/web
bun run test -- src/design-system/navigation/ProjectPanel.test.tsx src/pages/ApiKeysPage.test.tsx src/pages/agents/AgentCardModal.test.tsx
bun run build
```

Expected: pass and typecheck.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/design-system/navigation/ProjectPanel.tsx apps/web/src/pages/ProvidersPage.tsx apps/web/src/pages/ApiKeysPage.tsx apps/web/src/pages/agents/AgentCardModal.tsx apps/web/src/design-system/navigation/ProjectPanel.test.tsx
git commit -m "feat(web): confirm standard destructive actions"
```

---

### Task 11: Admin permission descriptions

**Files:**
- Create: `apps/web/src/pages/admin/permissionDescriptions.ts`
- Create: `apps/web/src/pages/admin/permissionDescriptions.test.ts`
- Modify: `apps/web/src/pages/AdminPage.tsx`

**Interfaces:**
- Produces: `describePermission(name: string, stored?: string | null): string`.

- [ ] **Step 1: Write the failing test**

```ts
// apps/web/src/pages/admin/permissionDescriptions.test.ts
import { describePermission } from "./permissionDescriptions";

test("prefers stored descriptions and falls back to built-ins", () => {
  expect(describePermission("projects:read", "Custom")).toBe("Custom");
  expect(describePermission("projects:read")).toContain("projects");
  expect(describePermission("custom:thing")).toBe("No description");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
cd apps/web
bun run test -- src/pages/admin/permissionDescriptions.test.ts
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement and wire the map**

```ts
// apps/web/src/pages/admin/permissionDescriptions.ts
const BUILT_INS: Record<string, string> = {
  "agents:create": "Create and update agent configurations.",
  "agents:read": "List and inspect agent configurations.",
  "agents:delete": "Delete agent configurations.",
  "providers:create": "Create and update model providers.",
  "providers:read": "List providers and their non-secret settings.",
  "providers:delete": "Delete model providers.",
  "providers:list-models": "Discover models from a provider endpoint.",
  "projects:create": "Create and update projects.",
  "projects:read": "List projects and open project workspaces.",
  "projects:delete": "Delete projects.",
  "sessions:create": "Create sessions, send messages, and rename sessions.",
  "sessions:read": "Read sessions, messages, plans, and diagnostics.",
  "users:manage": "Create and manage users.",
  "roles:manage": "Manage roles, permissions, and assignments.",
  "api_keys:manage": "Create, inspect, and revoke API keys.",
};

export function describePermission(name: string, stored?: string | null): string {
  const custom = stored?.trim();
  return custom || BUILT_INS[name] || "No description";
}
```

In `AdminPage`, use `describePermission(p.name, p.description)` and `describePermission(r.name, r.description)` in table cells. In `RolePermissionsModal`, use labels:

```tsx
data={permissions.map((p) => ({
  value: p.id,
  label: `${p.name} — ${describePermission(p.name, p.description)}`,
}))}
```

- [ ] **Step 4: Run the tests**

Run:

```powershell
cd apps/web
bun run test -- src/pages/admin/permissionDescriptions.test.ts
bun run build
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/pages/admin/permissionDescriptions.ts apps/web/src/pages/admin/permissionDescriptions.test.ts apps/web/src/pages/AdminPage.tsx
git commit -m "feat(web): describe core admin permissions"
```

---

### Task 12: Session title frontend

**Files:**
- Modify: `apps/web/src/api/endpoints.ts`
- Modify: `apps/web/src/api/queries.ts`
- Modify: `apps/web/src/design-system/navigation/ProjectPanel.tsx`
- Modify: `apps/web/src/pages/HomePage.tsx`
- Modify: `apps/web/src/pages/SessionPage.tsx`
- Modify: `apps/web/src/design-system/navigation/ProjectPanel.test.tsx`
- Modify: `apps/web/src/pages/HomePage.test.tsx`
- Modify: `apps/web/src/pages/SessionPage.chat.test.tsx`

**Interfaces:**
- Consumes: `SessionRow.title`, `SessionDetail.title`, `PATCH /sessions/{sid}`.
- Produces: `renameSession(sid, title)`, `useRenameSession()`.

- [ ] **Step 1: Write failing tests**

Add a `renameSessionMock` to the existing query mock:

```tsx
const renameSessionMock = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock("../../api/queries", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/queries")>();
  return {
    ...actual,
    useDeleteSession: () => ({ mutateAsync: deleteSessionMock }),
    useRenameSession: () => ({ mutateAsync: renameSessionMock }),
  };
});
```

Add to `ProjectPanel.test.tsx`:

```tsx
test("shows and renames a session title", async () => {
  vi.spyOn(endpoints, "fetchSessions").mockResolvedValueOnce([
    { id: "s1", project_id: "p1", agent_id: "ag", title: "Release plan", created_at: "t2" },
  ] as never);
  renderPanel();
  expect(await screen.findByText("Release plan")).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("Rename session s1"));
  fireEvent.change(screen.getByLabelText("Session title"), { target: { value: "Launch checklist" } });
  fireEvent.keyDown(screen.getByLabelText("Session title"), { key: "Enter" });
  await waitFor(() => expect(renameSessionMock).toHaveBeenCalledWith("s1", "Launch checklist"));
});
```

Add to `SessionPage.chat.test.tsx` a session with `title: "Release plan"` and assert the header shows it.

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
cd apps/web
bun run test -- src/design-system/navigation/ProjectPanel.test.tsx src/pages/SessionPage.chat.test.tsx
```

Expected: FAIL because titles and rename are not rendered.

- [ ] **Step 3: Implement the API and UI**

Add endpoints:

```ts
export async function renameSession(sid: string, title: string): Promise<Session> {
  const { data, error, response } = await api.PATCH("/sessions/{sid}", {
    params: { path: { sid } },
    body: { title },
  });
  if (error) throw toApiError(error, "Failed to rename session", response.status);
  return data as Session;
}
```

Add query:

```ts
export function useRenameSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ sid, title }: { sid: string; title: string }) => renameSession(sid, title),
    onSuccess: (_data, variables) => {
      void qc.invalidateQueries({ queryKey: ["sessions"] });
      void qc.invalidateQueries({ queryKey: ["session", variables.sid] });
    },
  });
}
```

In `ProjectPanel`, render:

```tsx
<span className={styles.sessionTitle}>{session.title ?? `Session ${index + 1}`}</span>
<IconButton
  label={`Rename session ${session.id}`}
  icon={RiPencilLine}
  size={16}
  onClick={() => setRenaming(session.id)}
/>
{renaming === session.id && (
  <TextInput
    aria-label="Session title"
    value={titleDraft}
    onChange={(event) => setTitleDraft(event.currentTarget.value)}
    onKeyDown={(event) => {
      if (event.key === "Enter") void saveTitle(session.id);
      if (event.key === "Escape") setRenaming(null);
    }}
    autoFocus
  />
)}
```

On save, trim the title, reject blanks, call `rename.mutateAsync({ sid, title })`, then clear edit state. Invalidate sessions after a successful chat by calling `qc.invalidateQueries` in `SessionPage.refresh()` for `["sessions"]` and `["session", id]`.

In `HomePage`, change the recent-session line from `session.agent_id` to:

```tsx
<strong>{session.title ?? session.agent_id}</strong>
```

In `SessionPage`, replace the `<h1>Session</h1>` with:

```tsx
<h1>{session?.title ?? "Session"}</h1>
<Button size="compact-xs" variant="light" onClick={() => setRenaming(true)}>
  Rename
</Button>
```

Render a small inline title input when `renaming` is true, plus `Save title` and `Cancel` buttons. Enter saves with `useRenameSession`, Escape cancels, and the Save button uses the same guarded save function:

- [ ] **Step 4: Run the tests and build**

Run:

```powershell
cd apps/web
bun run test -- src/design-system/navigation/ProjectPanel.test.tsx src/pages/HomePage.test.tsx src/pages/SessionPage.chat.test.tsx
bun run build
```

Expected: pass and typecheck.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/api/endpoints.ts apps/web/src/api/queries.ts apps/web/src/design-system/navigation/ProjectPanel.tsx apps/web/src/pages/HomePage.tsx apps/web/src/pages/SessionPage.tsx apps/web/src/design-system/navigation/ProjectPanel.test.tsx apps/web/src/pages/HomePage.test.tsx apps/web/src/pages/SessionPage.chat.test.tsx
git commit -m "feat(web): show and rename session titles"
```

---

### Task 13: Error states for projects, Home, providers, and agents

**Files:**
- Modify: `apps/web/src/design-system/navigation/ProjectPanel.tsx`
- Modify: `apps/web/src/pages/HomePage.tsx`
- Modify: `apps/web/src/pages/ProvidersPage.tsx`
- Modify: `apps/web/src/pages/AgentsPage.tsx`
- Modify: `apps/web/src/design-system/navigation/ProjectPanel.test.tsx`
- Modify: `apps/web/src/pages/HomePage.test.tsx`

**Interfaces:**
- Consumes: `ErrorState`.
- Produces: section/page error states with retry and no false empty data.

- [ ] **Step 1: Write failing tests**

Add to `ProjectPanel.test.tsx`:

```tsx
test("shows a retry state instead of an empty project list", async () => {
  vi.spyOn(endpoints, "fetchProjects").mockRejectedValueOnce(new Error("boom"));
  renderPanel();
  expect(await screen.findByText("Could not load projects")).toBeInTheDocument();
  expect(screen.queryByText("No projects")).not.toBeInTheDocument();
});
```

Add a `HomePage.test.tsx` case where `useProjects` returns `{ error: new ApiError("boom", 500) }` and assert “Could not load projects”.

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
cd apps/web
bun run test -- src/design-system/navigation/ProjectPanel.test.tsx src/pages/HomePage.test.tsx
```

Expected: FAIL because failures render the old empty/fallback behavior.

- [ ] **Step 3: Adopt `ErrorState`**

`ProjectPanel`:

```tsx
const { data: projects, isLoading, error, refetch } = useProjects();
...
if (error) {
  return <ErrorState title="Could not load projects" message={error.message} onRetry={() => void refetch()} />;
}
```

`AgentsPage`:

```tsx
const { data: agents, error, refetch } = useAgents();
if (error) {
  return <ErrorState title="Could not load agents" message={error.message} onRetry={() => void refetch()} />;
}
```

`ProvidersPage`:
- Providers tab: if `useProviders` errors, render `ErrorState` with `refetch`.
- Models tab: if `useModels` or `useProviders` errors, render `ErrorState` with the relevant retry.

`HomePage`:
- Destructure `error` and `refetch` for projects/sessions/agents/providers/models.
- For a failed recent-sessions or projects query, render a compact `ErrorState` inside the panel instead of “No sessions/projects”.
- For failed stat queries, render `—` rather than `0`.

- [ ] **Step 4: Run the tests**

Run:

```powershell
cd apps/web
bun run test -- src/design-system/navigation/ProjectPanel.test.tsx src/pages/HomePage.test.tsx
bun run build
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/design-system/navigation/ProjectPanel.tsx apps/web/src/pages/HomePage.tsx apps/web/src/pages/ProvidersPage.tsx apps/web/src/pages/AgentsPage.tsx apps/web/src/design-system/navigation/ProjectPanel.test.tsx apps/web/src/pages/HomePage.test.tsx
git commit -m "fix(web): surface project, home, provider, and agent read errors"
```

---

### Task 14: Error states for admin, API keys, skills, and session panels

**Files:**
- Modify: `apps/web/src/pages/AdminPage.tsx`
- Modify: `apps/web/src/pages/ApiKeysPage.tsx`
- Modify: `apps/web/src/pages/SkillsPage.tsx`
- Modify: `apps/web/src/pages/SessionPage.tsx`
- Modify: `apps/web/src/pages/ApiKeysPage.test.tsx`
- Modify: `apps/web/src/pages/SkillsPage.test.tsx`

**Interfaces:**
- Consumes: `ErrorState`.
- Produces: tab/section error states with retry for remaining pages.

- [ ] **Step 1: Write failing tests**

Add to `ApiKeysPage.test.tsx`:

```tsx
test("shows a retry state when keys fail to load", async () => {
  vi.spyOn(endpoints, "fetchApiKeys").mockRejectedValueOnce(new Error("boom"));
  renderPage();
  expect(await screen.findByText("Could not load API keys")).toBeInTheDocument();
});
```

Create `SkillsPage.test.tsx` with the same pattern for `fetchSkills` and “Could not load skills”.

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
cd apps/web
bun run test -- src/pages/ApiKeysPage.test.tsx src/pages/SkillsPage.test.tsx
```

Expected: FAIL because failures render empty states.

- [ ] **Step 3: Adopt `ErrorState`**

- `ApiKeysPage`: destructure `error` and `refetch`; render `ErrorState` above/instead of the key table. Keep the create-key form visible.
- `SkillsPage`: destructure `error` and `refetch`; render `ErrorState` instead of the table.
- `AdminPage`: each tab destructures `error` and `refetch`; render a tab-level `ErrorState` while keeping the create form available.
- `SessionPage`: if `useMessages` errors, render an `ErrorState` in the message pane with a Retry that calls `refetch`. If `useSessionPlan` errors, render a compact plan error row with Retry. LSP failures remain non-blocking but must not be silently reported as empty when the About panel is opened.

- [ ] **Step 4: Run the tests**

Run:

```powershell
cd apps/web
bun run test -- src/pages/ApiKeysPage.test.tsx src/pages/SkillsPage.test.tsx src/pages/AdminPage.test.tsx
bun run build
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/pages/AdminPage.tsx apps/web/src/pages/ApiKeysPage.tsx apps/web/src/pages/SkillsPage.tsx apps/web/src/pages/SessionPage.tsx apps/web/src/pages/ApiKeysPage.test.tsx apps/web/src/pages/SkillsPage.test.tsx
git commit -m "fix(web): surface remaining read errors"
```

---

### Task 15: UX-4 E2E coverage and existing-test updates

**Files:**
- Create: `apps/web/e2e/ux4-data-integrity.spec.ts`
- Modify: existing E2E specs that delete resources:
  - `apps/web/e2e/management.spec.ts`
  - `apps/web/e2e/provider-model-admin.spec.ts`
  - `apps/web/e2e/api-keys.spec.ts`
  - `apps/web/e2e/chat.spec.ts` if confirmation affects it

**Interfaces:**
- Consumes: all UX-4 UI and API behavior.
- Produces: end-to-end proof for errors, validation, not-found states, confirmations, titles, and active navigation.

- [ ] **Step 1: Write the new E2E spec**

```ts
import { expect, type APIRequestContext, type Page, test } from "@playwright/test";

const API = "http://localhost:8000";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByRole("textbox", { name: "Password" }).fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();
}

async function createSessionFixture(page: Page, request: APIRequestContext) {
  const token = await page.evaluate(() => {
    const raw = sessionStorage.getItem("agentbox-auth");
    return JSON.parse(raw as string).state.token as string;
  });
  const headers = { Authorization: `Bearer ${token}` };
  const suffix = Date.now();
  const project = await request.post(`${API}/projects`, {
    headers,
    data: { name: `e2e-ux4-project-${suffix}`, path: "." },
  });
  const projectBody = await project.json();
  const provider = await request.post(`${API}/providers`, {
    headers,
    data: { name: `e2e-ux4-provider-${suffix}`, kind: "test", models_url: "http://localhost:9999/models" },
  });
  const providerBody = await provider.json();
  await request.post(`${API}/providers/${providerBody.id}/models/refresh`, { headers });
  const agent = await request.post(`${API}/agents`, {
    headers,
    data: { name: `e2e-ux4-agent-${suffix}`, model: "e2e-model", tool_bindings: [] },
  });
  const agentBody = await agent.json();
  const session = await request.post(`${API}/sessions`, {
    headers,
    data: { project_id: projectBody.id, agent_id: agentBody.name },
  });
  const sessionBody = await session.json();
  return { projectName: projectBody.name, sessionId: sessionBody.id };
}

test("keeps active navigation on a direct route", async ({ page }) => {
  await login(page);
  await page.goto("/providers");
  await expect(page.getByRole("link", { name: "Providers" })).toHaveAttribute("aria-current", "page");
});

test("shows 404 and session-not-found states", async ({ page }) => {
  await login(page);
  await page.goto("/missing-route");
  await expect(page.getByRole("heading", { name: /page not found/i })).toBeVisible();
  await page.goto("/sessions/deadbeef");
  await expect(page.getByRole("heading", { name: /session not found/i })).toBeVisible();
  await expect(page.getByLabel("Message")).toHaveCount(0);
});

test("shows a retryable list error", async ({ page }) => {
  let calls = 0;
  await page.route("**/api/projects", async (route) => {
    calls += 1;
    if (calls === 1) {
      await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "database unavailable" }) });
    } else {
      await route.continue();
    }
  });
  await login(page);
  await expect(page.getByText("Could not load projects")).toBeVisible();
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("Could not load projects")).toBeHidden();
});

test("blocks blank project submission", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "New project" }).first().click();
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByText("Name is required.")).toBeVisible();
  await expect(page.getByText("Path is required.")).toBeVisible();
});

test("requires a typed project confirmation", async ({ page, request }) => {
  await login(page);
  const token = await page.evaluate(() => {
    const raw = sessionStorage.getItem("agentbox-auth");
    return JSON.parse(raw as string).state.token as string;
  });
  const headers = { Authorization: `Bearer ${token}` };
  const project = await request.post(`${API}/projects`, {
    headers,
    data: { name: `e2e-ux4-${Date.now()}`, path: "." },
  });
  const projectName = (await project.json()).name;
  await page.goto("/");
  await expect(page.getByText(projectName)).toBeVisible();
  await page.getByLabel(`Delete ${projectName}`).click();
  const confirm = page.getByRole("button", { name: "Delete project" });
  await expect(confirm).toBeDisabled();
  await page.getByLabel(`Type ${projectName} to confirm`).fill(projectName);
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await expect(page.getByText(projectName)).toBeHidden();
});

test("uses a standard session confirmation", async ({ page, request }) => {
  await login(page);
  const { sessionId } = await createSessionFixture(page, request);
  await page.goto("/");
  await page.getByLabel(`Delete session ${sessionId}`).click();
  await page.getByRole("button", { name: "Delete session" }).click();
  await expect(page.getByLabel(`Delete session ${sessionId}`)).toHaveCount(0);
});

test("renames a session title", async ({ page, request }) => {
  await login(page);
  const { sessionId } = await createSessionFixture(page, request);
  await page.goto(`/sessions/${sessionId}`);
  await page.getByRole("button", { name: "Rename" }).click();
  await page.getByLabel("Session title").fill("Release plan");
  await page.getByRole("button", { name: "Save title" }).click();
  await expect(page.getByRole("heading", { name: "Release plan" })).toBeVisible();
  await page.goto("/");
  await expect(page.getByText("Release plan")).toBeVisible();
});
```

- [ ] **Step 2: Update existing destructive-action tests**

Where an existing spec deletes a resource, add the confirmation step:

```ts
await page.getByRole("button", { name: "Delete" }).click();
await page.getByRole("button", { name: /delete/i }).last().click();
```

For high-tier resources, type the name first:

```ts
await page.getByLabel(/type .* to confirm/i).fill(resourceName);
```

- [ ] **Step 3: Run focused E2E**

Run:

```powershell
cd apps/web
bun run e2e/prepare.ts
bunx playwright test e2e/ux4-data-integrity.spec.ts e2e/management.spec.ts e2e/provider-model-admin.spec.ts e2e/api-keys.spec.ts
```

Expected: pass.

- [ ] **Step 4: Run the full E2E suite**

Run:

```powershell
cd apps/web
bun run e2e
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/e2e
git commit -m "test(web): cover UX-4 integrity and navigation flows"
```

---

### Task 16: UX-4 screenshot pack

**Files:**
- Create: `apps/web/scripts/screenshots-ux4.mjs`
- Create: `docs/reviews/2026-11-21-ux-4/README.md`
- Created assets: `docs/reviews/2026-11-21-ux-4/*.png`
- Create: `apps/web/src/design-system/patterns/ErrorState.stories.tsx`
- Create: `apps/web/src/design-system/forms/validation.stories.tsx`
- Modify: `apps/web/src/design-system/overlays/overlays.stories.tsx`

**Interfaces:**
- Consumes: built Storybook.
- Produces: deterministic visual evidence for the new states.

- [ ] **Step 1: Add Storybook stories**

Add `ErrorState.stories.tsx`:

```tsx
import type { Meta, StoryObj } from "@storybook/react-vite";

import { ErrorState } from "./ErrorState";

const meta: Meta<typeof ErrorState> = {
  title: "Patterns/ErrorStates",
  component: ErrorState,
};
export default meta;
type Story = StoryObj<typeof ErrorState>;

export const Error: Story = {
  args: {
    title: "Could not load projects",
    message: "The server could not be reached. Try again.",
    onRetry: () => {},
  },
};
```

Add `validation.stories.tsx`:

```tsx
import type { Meta, StoryObj } from "@storybook/react-vite";

import { FormField } from "./FormField";
import { TextInput } from "./TextInput";

function ValidationDemo() {
  return (
    <FormField label="Project name" required error="Name is required.">
      <TextInput value="" onChange={() => {}} />
    </FormField>
  );
}

const meta: Meta<typeof ValidationDemo> = {
  title: "Forms/Validation",
  component: ValidationDemo,
};
export default meta;
type Story = StoryObj<typeof ValidationDemo>;

export const Errors: Story = {};
```

In `overlays.stories.tsx`, add:

```tsx
export const StandardConfirm: Story = {
  render: () => (
    <ConfirmDialog
      opened
      title="Delete session?"
      description="This permanently deletes the session. This cannot be undone."
      confirmLabel="Delete session"
      danger
      onConfirm={() => {}}
      onClose={() => {}}
    />
  ),
};

export const TypeToConfirm: Story = {
  render: () => (
    <ConfirmDialog
      opened
      title="Delete project?"
      description="This permanently deletes the project. This cannot be undone."
      requireText="demo-project"
      confirmLabel="Delete project"
      danger
      onConfirm={() => {}}
      onClose={() => {}}
    />
  ),
};
```

- [ ] **Step 2: Add the screenshot script**

```js
// apps/web/scripts/screenshots-ux4.mjs
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const here = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(here, "../../../docs/reviews/2026-11-21-ux-4");
const base = "http://localhost:6006/iframe.html";
const desktop = { width: 1280, height: 900 };

const shots = [
  ["error-state", "patterns-error-states--error", desktop],
  ["confirm-standard", "overlays-overview--standard-confirm", desktop],
  ["confirm-typed", "overlays-overview--type-to-confirm", desktop],
  ["form-validation", "forms-validation--errors", desktop],
];

await mkdir(outDir, { recursive: true });
const browser = await chromium.launch();
for (const [name, id, viewport] of shots) {
  const page = await browser.newPage({ viewport, colorScheme: "dark" });
  await page.goto(`${base}?id=${id}&globals=theme:dark&viewMode=story`);
  await page.waitForSelector("#storybook-root", { timeout: 30000 });
  await page.waitForTimeout(600);
  await page.screenshot({
    path: path.join(outDir, `${name}.png`),
    fullPage: true,
    animations: "disabled",
  });
  await page.close();
  console.log(`saved ${name}.png`);
}
await browser.close();
```

- [ ] **Step 3: Build Storybook and capture screenshots**

Run:

```powershell
cd apps/web
bun run build-storybook
bun run preview-storybook
```

In another terminal:

```powershell
cd apps/web
bun run scripts/screenshots-ux4.mjs
```

Expected: PNG files exist in `docs/reviews/2026-11-21-ux-4/`.

- [ ] **Step 4: Add the README**

```md
# UX-4 data integrity and navigation screenshot pack

Deterministic Storybook captures. Dark theme.

## Error recovery

![Retryable error state](./error-state.png)

## Confirmation

![Standard confirmation](./confirm-standard.png)

![Type-to-confirm](./confirm-typed.png)

## Validation

![Form validation](./form-validation.png)
```

- [ ] **Step 5: Commit**

```powershell
git add apps/web/scripts/screenshots-ux4.mjs apps/web/src/design-system docs/reviews/2026-11-21-ux-4
git commit -m "docs(ux): add UX-4 screenshot pack"
```

---

### Task 17: Roadmap, final verification, and merge

**Files:**
- Modify: `docs/ROADMAP.md`
- Modify: `docs/superpowers/plans/2026-11-21-ux-4-data-integrity.md`
- Modify: `docs/superpowers/specs/2026-11-21-ux-4-data-integrity-design.md`

**Interfaces:**
- Produces: completed UX-4 cycle on `master`.

- [ ] **Step 1: Update roadmap and plan status**

- Set UX-4 to `DONE` in `docs/ROADMAP.md`.
- Update the paragraph to say UX-1 through UX-4 are complete; next cycle is not yet scheduled.
- Add history row 33 for UX-4 with the spec and plan paths.
- Add `**Status:** COMPLETE` under the plan title.
- Change the spec status to `Approved`.

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
uv run ruff check --fix packages
uv run ty check packages
```

Expected: all pass.

- [ ] **Step 3: Confirm screenshot assets**

Run:

```powershell
Get-ChildItem docs/reviews/2026-11-21-ux-4 -Filter *.png
```

Expected: `error-state.png`, `confirm-standard.png`, `confirm-typed.png`, `form-validation.png`.

- [ ] **Step 4: Commit the docs**

```powershell
git add docs/ROADMAP.md docs/superpowers/plans/2026-11-21-ux-4-data-integrity.md docs/superpowers/specs/2026-11-21-ux-4-data-integrity-design.md
git commit -m "docs: complete UX-4"
```

- [ ] **Step 5: Merge into master**

Run:

```powershell
git switch master
git merge --ff-only feat/ux-4-data-integrity
git status --short
```

Expected: fast-forward merge, clean working tree.

---

## Self-review

**Spec coverage:** Tasks 1 and 4 cover safe logging and typed errors. Task 5 covers error/404/session states. Tasks 2, 6, and 7 cover validation. Tasks 8-10 cover confirmations. Task 11 covers permission descriptions. Tasks 3 and 12 cover session titles. Tasks 13-14 cover remaining read errors. Tasks 15-17 cover E2E, visuals, roadmap, and verification.

**Placeholder scan:** No TBD/TODO steps; each task names exact files, tests, commands, and commits.

**Type consistency:** `ApiError`, `toApiError`, `createQueryClient`, `shouldRetry`, `ErrorState`, `NotFoundPage`, `SessionNotFound`, `validateProviderDraft`, `describePermission`, `derive_session_title`, and `useRenameSession` keep the same names across tasks.
