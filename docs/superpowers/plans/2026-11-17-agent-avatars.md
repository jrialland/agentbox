# Agent Avatars (RoboHash set1 default + custom photo) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` (or `subagent-driven-development`) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give agents a default avatar generated with RoboHash set #1 and let users upload a custom photo (normalized 300×300 PNG) or reset to the default; show avatars in agent management and the chat header.

**Architecture:** A backend `avatar` bytea column + `avatar_media_type` store normalized uploads; `GET /agents/{name}/avatar` (public) serves the custom image or a cached, deterministic RoboHash set1 PNG (seeded by the agent id); `PUT`/`DELETE` manage it. The SPA uses a shared `AgentAvatar` (Mantine `Avatar`) in the Agents page and the session chat header.

**Tech Stack:** FastAPI, SQLModel/Alembic, Pillow, `robohash` 2.x, React 19, Mantine v9, TanStack Query, Playwright.

## Global Constraints

- Defaults MUST come from **RoboHash set #1** (`roboset="set1"`); no other generator.
- Uploaded photos are normalized: center-crop square → 300×300 → PNG, metadata stripped; accept only `image/png|jpeg|webp`, ≤2 MB.
- `GET /agents/{name}/avatar` is **public** (an `<img>` cannot send a Bearer token); `PUT`/`DELETE` require `agents:create` (no `agents:update` exists).
- Add RoboHash/CC attribution to `NOTICE` + README; no in-app attribution.
- Keep `ruff`/`ty`/`bandit` clean; `bun run test` + `bun run build` must pass.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `packages/agentbox-api/src/agentbox_api/avatars.py` | RoboHash default generation + upload normalization |
| `packages/agentbox-models/src/agentbox_models/tables/core.py` | `Agent.avatar_data`, `avatar_media_type` |
| `packages/agentbox-models/alembic/versions/7a1c2f3d4e5b_agent_avatar.py` | migration |
| `packages/agentbox-api/src/agentbox_api/routers/agents.py` | avatar GET/PUT/DELETE |
| `packages/agentbox-api/src/agentbox_api/routers/sessions.py` | `SessionDetail` (+`agent_name`) |
| `apps/web/src/components/agents/AgentAvatar.tsx` | avatar widget |
| `apps/web/src/api/endpoints.ts` | `fetchSession`, `uploadAgentAvatar`, `resetAgentAvatar` |
| `apps/web/src/api/queries.ts` | `useSession`, `useUploadAvatar`, `useResetAvatar` |
| `apps/web/src/pages/AgentsPage.tsx` | create-photo picker + per-row change/remove |
| `apps/web/src/pages/SessionPage.tsx` | chat header (agent avatar + name) |
| `NOTICE`, `README.md` | RoboHash attribution |

---

### Task 1: Backend avatar service + deps + attribution

**Files:**
- Create: `packages/agentbox-api/src/agentbox_api/avatars.py`
- Create: `packages/agentbox-api/tests/test_avatars.py`
- Modify: `packages/agentbox-api/pyproject.toml`
- Create: `NOTICE`; Modify: `README.md`

**Interfaces:**
- Produces: `generate_default_avatar(seed: str, size: int = 300) -> bytes`; `normalize_upload(data: bytes) -> bytes`; constants `AVATAR_SIZE`, `MAX_UPLOAD_BYTES`, `ALLOWED_UPLOAD_TYPES`.

- [ ] **Step 1: Add dependencies**

Edit `packages/agentbox-api/pyproject.toml` `dependencies` to add:
```toml
    "robohash>=2.0",
    "pillow>=9.1",
```
Then run (repo root): `uv sync` — expect it to resolve/install `robohash`, `pillow`, `natsort`.

- [ ] **Step 2: Write the failing tests**

Create `packages/agentbox-api/tests/test_avatars.py`:
```python
import io

import pytest
from PIL import Image

from agentbox_api.avatars import generate_default_avatar, normalize_upload


def test_default_avatar_is_deterministic_png():
    a = generate_default_avatar("agent-1")
    b = generate_default_avatar("agent-1")
    assert a[:8] == b"\x89PNG\r\n\x1a\n"
    assert a == b


def test_normalize_upload_square_png():
    img = Image.new("RGB", (400, 200), "red")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    out = normalize_upload(buf.getvalue())
    with Image.open(io.BytesIO(out)) as im:
        assert im.format == "PNG"
        assert im.size == (300, 300)


def test_normalize_rejects_garbage():
    with pytest.raises(ValueError):
        normalize_upload(b"not an image")
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest packages/agentbox-api/tests/test_avatars.py -q`
Expected: FAIL (ModuleNotFoundError: agentbox_api.avatars).

- [ ] **Step 4: Implement `avatars.py`**

```python
"""Agent avatar generation (RoboHash set1 default) and upload normalization."""

from __future__ import annotations

import io
from functools import lru_cache

from PIL import Image, UnidentifiedImageError
from robohash import Robohash

AVATAR_SIZE = 300
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
ALLOWED_UPLOAD_TYPES = {"image/png", "image/jpeg", "image/webp"}


@lru_cache(maxsize=512)
def _render_default(seed: str, size: int) -> bytes:
    rh = Robohash(seed)
    rh.assemble(roboset="set1", sizex=size, sizey=size, format="png")
    buf = io.BytesIO()
    rh.img.save(buf, format="PNG")
    return buf.getvalue()


def generate_default_avatar(seed: str, size: int = AVATAR_SIZE) -> bytes:
    return _render_default(seed, size)


def normalize_upload(data: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGB")
            w, h = img.size
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            img = img.crop((left, top, left + side, top + side))
            img = img.resize((AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            img.save(out, format="PNG")
            return out.getvalue()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("invalid image") from exc
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest packages/agentbox-api/tests/test_avatars.py -q`
Expected: 3 passed.

- [ ] **Step 6: Attribution**

Create `NOTICE` (repo root):
```
Agentbox uses RoboHash for default agent avatars.

RoboHash (https://github.com/e1ven/Robohash, https://robohash.org)
  Code: MIT/Expat license, Copyright (c) 2011, e1ven.
  Set 1 artwork ("Classic robots"): Zikri Kader, licensed CC-BY-3.0 / CC-BY-4.0.
  "Robots lovingly delivered by Robohash.org."
```
Append a `## Credits` section to `README.md`:
```markdown
## Credits

Default agent avatars are generated with [RoboHash](https://robohash.org) (set 1). RoboHash code is MIT-licensed (Copyright (c) 2011, e1ven); set 1 artwork is by Zikri Kader, CC-BY-3.0/CC-BY-4.0. "Robots lovingly delivered by Robohash.org."
```

- [ ] **Step 7: Commit**

```bash
git add packages/agentbox-api/pyproject.toml uv.lock packages/agentbox-api/src/agentbox_api/avatars.py packages/agentbox-api/tests/test_avatars.py NOTICE README.md
git commit -m "feat(api): RoboHash set1 avatar generation + upload normalization"
```

---

### Task 2: Backend schema + migration

**Files:**
- Modify: `packages/agentbox-models/src/agentbox_models/tables/core.py`
- Create: `packages/agentbox-models/alembic/versions/7a1c2f3d4e5b_agent_avatar.py`
- Create: `packages/agentbox-api/tests/test_agent_avatar_schema.py`

**Interfaces:**
- Produces: `Agent.avatar_data: bytes | None`, `Agent.avatar_media_type: str | None`.

- [ ] **Step 1: Write the failing test**

Create `packages/agentbox-api/tests/test_agent_avatar_schema.py`:
```python
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import Agent, Model, Provider


async def test_agent_avatar_columns_roundtrip():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(Provider(id="p", name="t", kind="generic"))
        s.add(Model(id="m", provider_id="p", name="mm"))
        s.add(
            Agent(
                id="a",
                name="a",
                description="",
                instructions="",
                model_id="m",
                avatar_data=b"\x89PNG",
                avatar_media_type="image/png",
            )
        )
        await s.commit()
    async with factory() as s:
        a = await s.get(Agent, "a")
        assert a.avatar_data == b"\x89PNG"
        assert a.avatar_media_type == "image/png"
    await engine.dispose()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/agentbox-api/tests/test_agent_avatar_schema.py -q`
Expected: FAIL (unexpected keyword `avatar_data`).

- [ ] **Step 3: Add the columns**

In `core.py`, in `Agent`, after `avatar_url`:
```python
    avatar_data: bytes | None = Field(
        default=None, sa_column=Column(LargeBinary, nullable=True)
    )
    avatar_media_type: str | None = None
```
(`Column`, `LargeBinary`, `Field` are already imported.)

- [ ] **Step 4: Add the migration**

Create `packages/agentbox-models/alembic/versions/7a1c2f3d4e5b_agent_avatar.py`:
```python
"""agent avatar

Revision ID: 7a1c2f3d4e5b
Revises: 518db7d88349
Create Date: 2026-11-19 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a1c2f3d4e5b"
down_revision: str | Sequence[str] | None = "518db7d88349"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent", sa.Column("avatar_data", sa.LargeBinary(), nullable=True))
    op.add_column("agent", sa.Column("avatar_media_type", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent", "avatar_media_type")
    op.drop_column("agent", "avatar_data")
```

- [ ] **Step 5: Run tests + commit**

Run: `uv run pytest packages/agentbox-api/tests/test_agent_avatar_schema.py -q` → 1 passed.
```bash
git add packages/agentbox-models/src/agentbox_models/tables/core.py packages/agentbox-models/alembic/versions/7a1c2f3d4e5b_agent_avatar.py packages/agentbox-api/tests/test_agent_avatar_schema.py
git commit -m "feat(models): agent avatar blob columns + migration"
```

---

### Task 3: Backend avatar endpoints + session detail + schema regen

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/routers/agents.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`
- Create: `packages/agentbox-api/tests/test_avatar_endpoints.py`
- Regenerate: `apps/web/openapi.json`, `apps/web/src/api/schema.d.ts`

**Interfaces:**
- Produces: `GET/PUT/DELETE /agents/{name}/avatar`; `GET /sessions/{sid}` returns `SessionDetail { id, project_id, agent_id, agent_name, head_turn_id, created_at }`.

- [ ] **Step 1: Write the failing tests**

Create `packages/agentbox-api/tests/test_avatar_endpoints.py`:
```python
import io

import httpx
from PIL import Image

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
from agentbox_models.tables.core import Agent, Model, Project, Provider, SessionRow


async def _setup():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw")))
        s.add(Role(id="r_u1", name="role"))
        for i, p in enumerate(["agents:create", "agents:read", "sessions:read"]):
            s.add(Permission(id=f"p{i}_u1", name=p))
            s.add(RolePermissionLink(role_id="r_u1", permission_id=f"p{i}_u1"))
        s.add(UserRoleLink(user_id="u1", role_id="r_u1"))
        s.add(Provider(id="prov", name="test", kind="test"))
        s.add(Model(id="m", provider_id="prov", name="test-model"))
        s.add(Agent(id="ag", name="bot", description="", instructions="", model_id="m"))
        s.add(Project(id="prj", name="p", path=".", owner_id="u1"))
        s.add(SessionRow(id="s1", project_id="prj", agent_id="ag"))
        await s.commit()
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return engine, client


def _png(size=(400, 200)) -> bytes:
    img = Image.new("RGB", size, "red")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


async def _auth(client) -> dict:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_default_avatar_public_and_deterministic():
    engine, client = await _setup()
    try:
        r1 = await client.get("/agents/bot/avatar")
        r2 = await client.get("/agents/bot/avatar")
        assert r1.status_code == 200
        assert r1.headers["content-type"] == "image/png"
        assert r1.content == r2.content
    finally:
        await client.aclose()
        await engine.dispose()


async def test_unknown_agent_404():
    engine, client = await _setup()
    try:
        assert (await client.get("/agents/nope/avatar")).status_code == 404
    finally:
        await client.aclose()
        await engine.dispose()


async def test_upload_then_reset():
    engine, client = await _setup()
    try:
        h = await _auth(client)
        before = (await client.get("/agents/bot/avatar")).content
        up = await client.put(
            "/agents/bot/avatar",
            files={"file": ("a.png", _png(), "image/png")},
            headers=h,
        )
        assert up.status_code == 204
        after = await client.get("/agents/bot/avatar")
        assert after.content != before
        with Image.open(io.BytesIO(after.content)) as im:
            assert im.size == (300, 300)
        rm = await client.delete("/agents/bot/avatar", headers=h)
        assert rm.status_code == 204
        assert (await client.get("/agents/bot/avatar")).content == before
    finally:
        await client.aclose()
        await engine.dispose()


async def test_upload_rejects_bad_type_and_size():
    engine, client = await _setup()
    try:
        h = await _auth(client)
        bad = await client.put(
            "/agents/bot/avatar",
            files={"file": ("a.txt", b"x", "text/plain")},
            headers=h,
        )
        assert bad.status_code == 415
        big = await client.put(
            "/agents/bot/avatar",
            files={"file": ("a.png", b"x" * (2 * 1024 * 1024 + 1), "image/png")},
            headers=h,
        )
        assert big.status_code == 413
    finally:
        await client.aclose()
        await engine.dispose()


async def test_session_detail_has_agent_name():
    engine, client = await _setup()
    try:
        h = await _auth(client)
        r = await client.get("/sessions/s1", headers=h)
        assert r.status_code == 200
        assert r.json()["agent_name"] == "bot"
    finally:
        await client.aclose()
        await engine.dispose()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/agentbox-api/tests/test_avatar_endpoints.py -q`
Expected: FAIL (404 on `/agents/bot/avatar`, missing `agent_name`).

- [ ] **Step 3: Implement the avatar endpoints**

In `routers/agents.py`, add imports and routes:
```python
import hashlib

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from sqlmodel import select

from agentbox_api import avatars
from agentbox_models.tables.core import Agent
```
Routes:
```python
@router.get("/{name}/avatar")
async def get_avatar(name: str, request: Request):
    factory = request.app.state.session_factory
    async with factory() as s:
        agent = (
            await s.execute(select(Agent).where(Agent.name == name))
        ).scalars().first()
    if agent is None:
        raise HTTPException(status_code=404, detail="Not found")
    if agent.avatar_data:
        data = agent.avatar_data
        media = agent.avatar_media_type or "image/png"
    else:
        data = avatars.generate_default_avatar(agent.id)
        media = "image/png"
    etag = '"' + hashlib.sha256(data).hexdigest() + '"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    return Response(
        content=data,
        media_type=media,
        headers={"ETag": etag, "Cache-Control": "no-cache"},
    )


@router.put("/{name}/avatar")
async def upload_avatar(
    name: str,
    request: Request,
    file: UploadFile = File(...),
    _=Depends(require_permission("agents:create")),
):
    if file.content_type not in avatars.ALLOWED_UPLOAD_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported image type")
    data = await file.read()
    if len(data) > avatars.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image too large")
    try:
        normalized = avatars.normalize_upload(data)
    except ValueError:
        raise HTTPException(status_code=415, detail="Invalid image") from None
    factory = request.app.state.session_factory
    async with factory() as s:
        agent = (
            await s.execute(select(Agent).where(Agent.name == name))
        ).scalars().first()
        if agent is None:
            raise HTTPException(status_code=404, detail="Not found")
        agent.avatar_data = normalized
        agent.avatar_media_type = "image/png"
        s.add(agent)
        await s.commit()
    return Response(status_code=204)


@router.delete("/{name}/avatar")
async def reset_avatar(
    name: str,
    request: Request,
    _=Depends(require_permission("agents:create")),
):
    factory = request.app.state.session_factory
    async with factory() as s:
        agent = (
            await s.execute(select(Agent).where(Agent.name == name))
        ).scalars().first()
        if agent is None:
            raise HTTPException(status_code=404, detail="Not found")
        agent.avatar_data = None
        agent.avatar_media_type = None
        s.add(agent)
        await s.commit()
    return Response(status_code=204)
```

- [ ] **Step 4: Add `SessionDetail`**

In `routers/sessions.py`, add the model and replace `get_session`:
```python
class SessionDetail(BaseModel):
    id: str
    project_id: str
    agent_id: str
    agent_name: str
    head_turn_id: str | None = None
    created_at: str


@router.get("/{sid}", response_model=SessionDetail)
async def get_session(
    sid: str, request: Request, _=Depends(require_permission("sessions:read"))
):
    async with request.app.state.session_factory() as s:
        row = (
            await s.execute(select(SessionRow).where(SessionRow.id == sid))
        ).scalars().first()
        if row is None:
            raise HTTPException(status_code=404, detail="Not found")
        agent = (
            await s.execute(select(Agent).where(Agent.id == row.agent_id))
        ).scalars().first()
    return SessionDetail(
        id=row.id,
        project_id=row.project_id,
        agent_id=row.agent_id,
        agent_name=agent.name if agent is not None else "",
        head_turn_id=row.head_turn_id,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest packages/agentbox-api/tests/test_avatar_endpoints.py -q`
Expected: 5 passed.
Then run the full suite to catch regressions from the `SessionDetail` change:
`uv run pytest packages/agentbox-api/tests -q` → all pass.

- [ ] **Step 6: Regenerate the client schema**

```bash
uv run python -c "import json; from agentbox_api.app import create_app; from agentbox_api.config import Settings; open('apps/web/openapi.json','w',encoding='utf-8').write(json.dumps(create_app(Settings(jwt_secret='x'*32)).openapi(), indent=2))"
```
```powershell
Set-Location apps/web; bun run codegen
```
Expected: `schema.d.ts` now contains `/agents/{name}/avatar` and `SessionDetail`.

- [ ] **Step 7: Lint + commit**

Run: `uv run ruff check packages/agentbox-api` → clean.
```bash
git add packages/agentbox-api/src/agentbox_api/routers/agents.py packages/agentbox-api/src/agentbox_api/routers/sessions.py packages/agentbox-api/tests/test_avatar_endpoints.py apps/web/openapi.json apps/web/src/api/schema.d.ts
git commit -m "feat(api): agent avatar endpoints + session detail agent_name"
```

---

### Task 4: Frontend `AgentAvatar` + API helpers

**Files:**
- Create: `apps/web/src/components/agents/AgentAvatar.tsx`
- Create: `apps/web/src/components/agents/AgentAvatar.test.tsx`
- Modify: `apps/web/src/api/endpoints.ts`
- Modify: `apps/web/src/api/queries.ts`
- Create: `apps/web/src/api/avatar-endpoints.test.ts`

**Interfaces:**
- Produces: `<AgentAvatar name version? size? />`; `fetchSession`, `uploadAgentAvatar`, `resetAgentAvatar`; `useSession`, `useUploadAvatar`, `useResetAvatar`.

- [ ] **Step 1: Write the failing tests**

`AgentAvatar.test.tsx`:
```tsx
import { MantineProvider } from "@mantine/core";
import { render } from "@testing-library/react";

import { AgentAvatar } from "./AgentAvatar";

test("renders the avatar image with the agent name and version", () => {
  const { container } = render(
    <MantineProvider>
      <AgentAvatar name="bot" version={2} />
    </MantineProvider>,
  );
  const img = container.querySelector("img");
  expect(img?.getAttribute("src")).toContain("/agents/bot/avatar?v=2");
});
```

`avatar-endpoints.test.ts`:
```ts
import { vi } from "vitest";

import { resetAgentAvatar, uploadAgentAvatar } from "./endpoints";

test("uploadAgentAvatar PUTs multipart", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true });
  vi.stubGlobal("fetch", fetchMock);
  await uploadAgentAvatar(
    "bot",
    new File([new Uint8Array([1])], "a.png", { type: "image/png" }),
  );
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toContain("/agents/bot/avatar");
  expect(init.method).toBe("PUT");
  expect(init.body).toBeInstanceOf(FormData);
});

test("resetAgentAvatar DELETEs", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true });
  vi.stubGlobal("fetch", fetchMock);
  await resetAgentAvatar("bot");
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toContain("/agents/bot/avatar");
  expect(init.method).toBe("DELETE");
});
```

- [ ] **Step 2: Run to verify it fails**

```powershell
Set-Location apps/web; bun run test
```
Expected: FAIL (module not found / functions missing).

- [ ] **Step 3: Implement `AgentAvatar`**

```tsx
import { Avatar } from "@mantine/core";

import { API_URL } from "../../config";

export function AgentAvatar({
  name,
  version = 0,
  size = "md",
}: {
  name: string;
  version?: number;
  size?: number | string;
}) {
  const src = `${API_URL}/agents/${encodeURIComponent(name)}/avatar?v=${version}`;
  return <Avatar src={src} alt={name} name={name} radius="xl" size={size} />;
}
```

- [ ] **Step 4: Add endpoints**

In `endpoints.ts`: add `import { API_URL } from "../config";` at the top, change `uploadAttachment` to use `base = API_URL`, and add:
```ts
export type SessionDetail = components["schemas"]["SessionDetail"];

export async function fetchSession(sid: string): Promise<SessionDetail> {
  const { data, error } = await api.GET("/sessions/{sid}", {
    params: { path: { sid } },
  });
  if (error) throw new Error("Failed to fetch session");
  return data as SessionDetail;
}

export async function uploadAgentAvatar(name: string, file: File): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  const token = useAuthStore.getState().token;
  const r = await fetch(`${API_URL}/agents/${encodeURIComponent(name)}/avatar`, {
    method: "PUT",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!r.ok) throw new Error("avatar upload failed");
}

export async function resetAgentAvatar(name: string): Promise<void> {
  const token = useAuthStore.getState().token;
  const r = await fetch(`${API_URL}/agents/${encodeURIComponent(name)}/avatar`, {
    method: "DELETE",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!r.ok) throw new Error("avatar reset failed");
}
```

- [ ] **Step 5: Add hooks**

In `queries.ts`, add the imports (`fetchSession`, `resetAgentAvatar`, `uploadAgentAvatar`) and:
```ts
export function useSession(sessionId: string) {
  return useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => fetchSession(sessionId),
    enabled: !!sessionId,
  });
}

export function useUploadAvatar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, file }: { name: string; file: File }) =>
      uploadAgentAvatar(name, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      qc.invalidateQueries({ queryKey: ["session"] });
    },
  });
}

export function useResetAvatar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => resetAgentAvatar(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      qc.invalidateQueries({ queryKey: ["session"] });
    },
  });
}
```

- [ ] **Step 6: Run tests + commit**

```powershell
Set-Location apps/web; bun run test
```
Expected: all tests pass (including the 3 new).
```bash
git add apps/web/src/components/agents/AgentAvatar.tsx apps/web/src/components/agents/AgentAvatar.test.tsx apps/web/src/api/endpoints.ts apps/web/src/api/queries.ts apps/web/src/api/avatar-endpoints.test.ts
git commit -m "feat(web): AgentAvatar + avatar/session API helpers"
```

---

### Task 5: Agents page — create photo + per-row change/remove

**Files:**
- Modify: `apps/web/src/pages/AgentsPage.tsx`
- Create: `apps/web/src/pages/AgentsPage.test.tsx`

**Interfaces:**
- Consumes: `AgentAvatar`, `useUploadAvatar`, `useResetAvatar`.

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/pages/AgentsPage.test.tsx`:
```tsx
import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("../api/queries", () => ({
  useAgents: () => ({ data: [{ name: "bot", description: "d" }] }),
  useModels: () => ({ data: [] }),
  useCreateAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteAgent: () => ({ mutate: vi.fn() }),
  useUploadAvatar: () => ({ mutateAsync: vi.fn() }),
  useResetAvatar: () => ({ mutateAsync: vi.fn() }),
}));

import { AgentsPage } from "./AgentsPage";

test("renders an avatar for each agent", () => {
  render(
    <MantineProvider>
      <AgentsPage />
    </MantineProvider>,
  );
  expect(screen.getByRole("img", { name: "bot" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

```powershell
Set-Location apps/web; bun run test AgentsPage
```
Expected: FAIL (no img with name "bot").

- [ ] **Step 3: Update `AgentsPage`**

Add imports:
```tsx
import { AgentAvatar } from "../components/agents/AgentAvatar";
import {
  useAgents,
  useCreateAgent,
  useDeleteAgent,
  useModels,
  useResetAvatar,
  useUploadAvatar,
} from "../api/queries";
```
Add hooks/state in the component:
```tsx
  const upload = useUploadAvatar();
  const reset = useResetAvatar();
  const [photo, setPhoto] = useState<File | null>(null);
  const [versions, setVersions] = useState<Record<string, number>>({});
```
In `onCreate`, after `create.mutateAsync(...)`, replace the resets block with:
```tsx
      const created = await create.mutateAsync({
        name,
        description,
        instructions,
        model,
        tool_bindings,
        mode_definitions,
        sub_agent_ids: subAgents,
      });
      if (photo) {
        await upload.mutateAsync({ name: created.name, file: photo });
        setVersions((v) => ({ ...v, [created.name]: (v[created.name] ?? 0) + 1 }));
      }
      setPhoto(null);
      setName("");
      setDescription("");
      setInstructions("");
      setModel(null);
      setTools([]);
      setMcpServers([]);
      setSubAgents([]);
```
Add a Photo picker before the Create button:
```tsx
        <div>
          <p className="label">Photo</p>
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            aria-label="Photo"
            onChange={(e) => setPhoto(e.currentTarget.files?.[0] ?? null)}
          />
        </div>
```
In the table, add an `Avatar` header and cell:
```tsx
            <Table.Th>Avatar</Table.Th>
...
              <Table.Td>
                <AgentAvatar name={a.name} version={versions[a.name] ?? 0} />
              </Table.Td>
```
Replace the Actions cell with:
```tsx
              <Table.Td>
                <input
                  id={`avatar-${a.name}`}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  aria-label={`Change photo ${a.name}`}
                  style={{ display: "none" }}
                  onChange={async (e) => {
                    const file = e.currentTarget.files?.[0];
                    if (!file) return;
                    try {
                      await upload.mutateAsync({ name: a.name, file });
                      setVersions((v) => ({ ...v, [a.name]: (v[a.name] ?? 0) + 1 }));
                    } catch {
                      notifications.show({ message: "Failed to upload photo", color: "red" });
                    }
                  }}
                />
                <Button size="xs" onClick={() => document.getElementById(`avatar-${a.name}`)?.click()}>
                  Change photo
                </Button>{" "}
                <Button
                  size="xs"
                  variant="light"
                  onClick={async () => {
                    await reset.mutateAsync(a.name);
                    setVersions((v) => ({ ...v, [a.name]: (v[a.name] ?? 0) + 1 }));
                  }}
                >
                  Remove photo
                </Button>{" "}
                <Button size="xs" color="red" onClick={() => del.mutate(a.name)}>
                  Delete
                </Button>
              </Table.Td>
```

- [ ] **Step 4: Run tests + commit**

```powershell
Set-Location apps/web; bun run test
```
Expected: pass.
```bash
git add apps/web/src/pages/AgentsPage.tsx apps/web/src/pages/AgentsPage.test.tsx
git commit -m "feat(web): agent photo picker + per-row change/remove"
```

---

### Task 6: Chat header (agent avatar + name)

**Files:**
- Modify: `apps/web/src/pages/SessionPage.tsx`
- Create: `apps/web/src/pages/SessionPage.avatar.test.tsx`

**Interfaces:**
- Consumes: `useSession`, `AgentAvatar`.

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/pages/SessionPage.avatar.test.tsx`:
```tsx
import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

vi.mock("../api/queries", () => ({
  useMessages: () => ({ data: [] }),
  useSession: () => ({ data: { agent_name: "bot" } }),
}));

import { SessionPage } from "./SessionPage";

test("shows the agent avatar and name in the chat header", () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MantineProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/sessions/s1"]}>
          <Routes>
            <Route path="/sessions/:id" element={<SessionPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
  expect(screen.getByTestId("session-agent")).toHaveTextContent("bot");
  expect(screen.getByRole("img", { name: "bot" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

```powershell
Set-Location apps/web; bun run test SessionPage.avatar
```
Expected: FAIL (no `session-agent`).

- [ ] **Step 3: Add the header**

In `SessionPage.tsx`:
```tsx
import { AgentAvatar } from "../components/agents/AgentAvatar";
import { useMessages, useSession } from "../api/queries";
```
In the component:
```tsx
  const { data: session } = useSession(id);
```
Insert before `<h1 className="title">Session</h1>`:
```tsx
        {session && (
          <div
            className="is-flex is-align-items-center"
            style={{ gap: 8, marginBottom: "0.75rem" }}
            data-testid="session-agent"
          >
            <AgentAvatar name={session.agent_name} />
            <span className="has-text-weight-semibold">{session.agent_name}</span>
          </div>
        )}
```

- [ ] **Step 4: Update the existing SessionPage test**

In `apps/web/src/pages/SessionPage.test.tsx`, after the `fetchMessages` spy, add:
```tsx
  vi.spyOn(endpoints, "fetchSession").mockResolvedValue({ agent_name: "bot" } as never);
```
(So the new `useSession` call doesn't hit the network in that test.)

- [ ] **Step 5: Run tests + build + commit**

```powershell
Set-Location apps/web; bun run test; bun run build
```
Expected: pass.
```bash
git add apps/web/src/pages/SessionPage.tsx apps/web/src/pages/SessionPage.avatar.test.tsx
git commit -m "feat(web): show agent avatar + name in chat header"
```

---

### Task 7: E2E — default, upload, reset, chat header

**Files:**
- Create: `apps/web/e2e/avatars.spec.ts`

- [ ] **Step 1: Write the spec**

```ts
import { type APIRequestContext, expect, type Page, test } from "@playwright/test";

const API = "http://localhost:8000";
const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC",
  "base64",
);

async function setup(page: Page, request: APIRequestContext) {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  const raw = await page.evaluate(() => sessionStorage.getItem("agentbox-auth"));
  const token = JSON.parse(raw as string).state.token as string;
  const h = { Authorization: `Bearer ${token}` };

  const suffix = Date.now();
  const prov = await request.post(`${API}/providers`, {
    headers: h,
    data: { name: `e2e-av-${suffix}`, kind: "test", models_url: "http://localhost:9999/models" },
  });
  const provId = (await prov.json()).id;
  await request.post(`${API}/providers/${provId}/models/refresh`, { headers: h });

  const agentName = `e2e-av-agent-${suffix}`;
  await request.post(`${API}/agents`, {
    headers: h,
    data: {
      name: agentName,
      description: "d",
      instructions: "i",
      model: "e2e-model",
      tool_bindings: [],
      mode_definitions: [],
      sub_agent_ids: [],
    },
  });

  const proj = await request.post(`${API}/projects`, {
    headers: h,
    data: { name: `e2e-av-proj-${suffix}`, path: "." },
  });
  const projId = (await proj.json()).id;
  const sess = await request.post(`${API}/sessions`, {
    headers: h,
    data: { project_id: projId, agent_id: agentName },
  });
  return { agentName, sessionId: (await sess.json()).id };
}

test("agent avatars: default, upload, reset, chat header", async ({ page, request }) => {
  const { agentName, sessionId } = await setup(page, request);

  await page.goto("/agents");
  await page.waitForLoadState("networkidle");
  const row = page.getByRole("row", { name: new RegExp(agentName) });
  const img = row.locator("img");
  await expect(img).toBeVisible();
  await expect(img).toHaveAttribute("src", /v=0/);

  await row
    .getByLabel(`Change photo ${agentName}`)
    .setInputFiles({ name: "a.png", mimeType: "image/png", buffer: TINY_PNG });
  await expect(row.locator("img")).toHaveAttribute("src", /v=1/);

  await row.getByRole("button", { name: "Remove photo" }).click();
  await expect(row.locator("img")).toHaveAttribute("src", /v=2/);

  await page.goto(`/sessions/${sessionId}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByTestId("session-agent")).toContainText(agentName);
  await expect(
    page.getByTestId("session-agent").getByRole("img", { name: agentName }),
  ).toBeVisible();
});
```

- [ ] **Step 2: Run E2E**

```powershell
Set-Location apps/web; bun run e2e
```
Expected: all specs pass (management, chat, mcp-apps, avatars).

- [ ] **Step 3: Commit**

```bash
git add apps/web/e2e/avatars.spec.ts
git commit -m "test(web): E2E agent avatars (default/upload/reset/header)"
```

---

## Notes

- The E2E uses `admin` (which has `agents:create`, `agents:read`, `sessions:read`) and the `test` provider/model `e2e-model` from the stub server.
- `GET /agents/{name}/avatar` being public means the sandboxed `<img>` works; it is intentional and non-sensitive.
- `robohash`'s set1 artwork requires the `NOTICE`/README attribution (Task 1).
- Regenerate `openapi.json`/`schema.d.ts` whenever the avatar/session routes change (Task 3 does it once).
