# Provider / Model Management + Session Delete — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:executing-plans` (or `subagent-driven-development`). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Let admins edit providers, manage models directly, and delete sessions — from the UI, with safe backend guards.

**Architecture:** Backend adds `PUT /providers/{pid}`, `POST/DELETE /models`, `DELETE /sessions/{sid}`, and a shared `delete_session_data` helper; the Providers page becomes tabbed (Providers/Models); the project tree gains session delete.

**Tech Stack:** FastAPI, SQLModel, React 19, Mantine v9, TanStack Query, Playwright.

## Global Constraints

- Reuse `providers:create` (provider update + model mutations) and `sessions:create` (session delete); `providers:delete` for provider delete.
- Refuse (409) to delete a model in use, or a provider whose models are in use.
- No DB migration; API-level checks.
- `ruff`/`ty`/`bandit` clean; `bun run test`/`bun run build` pass.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `.../routers/providers.py` | provider update + safe delete |
| `.../routers/models.py` | model create/delete |
| `.../routers/sessions.py` | session delete |
| `.../runtime.py` | `delete_session_data` |
| `.../acp_server.py` | reuse `delete_session_data` |
| `apps/web/src/pages/ProvidersPage.tsx` | Providers/Models tabs |
| `apps/web/src/components/projects/ProjectTree.tsx` | session delete |
| `apps/web/src/api/endpoints.ts`, `queries.ts` | helpers + hooks |
| `apps/web/e2e/provider-model-admin.spec.ts` | E2E |

---

### Task 1: Backend — provider update + safe delete

**Files:** `routers/providers.py`; create `tests/test_provider_model_admin.py`.

- [ ] **Step 1: Write failing tests**

```python
import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import Permission, Role, RolePermissionLink, User, UserRoleLink
from agentbox_models.tables.core import Agent, Model, Provider


async def _setup(perms=("providers:create", "providers:read", "providers:delete")):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw")))
        s.add(Role(id="r1", name="role"))
        for i, p in enumerate(perms):
            s.add(Permission(id=f"p{i}", name=p))
            s.add(RolePermissionLink(role_id="r1", permission_id=f"p{i}"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(Provider(id="prov", name="old", kind="generic", api_key="secret"))
        s.add(Model(id="m1", provider_id="prov", name="m"))
        await s.commit()
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return engine, client, factory


async def _auth(client) -> dict:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_provider_update_preserves_api_key_when_omitted():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        r = await client.put("/providers/prov", json={"name": "new"}, headers=h)
        assert r.json()["name"] == "new"
        async with factory() as s:
            assert (await s.get(Provider, "prov")).api_key == "secret"
    finally:
        await client.aclose()
        await engine.dispose()


async def test_provider_delete_blocked_when_model_in_use():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        async with factory() as s:
            s.add(Agent(id="ag", name="a", description="", instructions="", model_id="m1"))
            await s.commit()
        r = await client.delete("/providers/prov", headers=h)
        assert r.status_code == 409
    finally:
        await client.aclose()
        await engine.dispose()


async def test_provider_delete_cascades_models():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        r = await client.delete("/providers/prov", headers=h)
        assert r.status_code == 200
        async with factory() as s:
            assert await s.get(Provider, "prov") is None
            assert await s.get(Model, "m1") is None
    finally:
        await client.aclose()
        await engine.dispose()
```

- [ ] **Step 2: Run to verify it fails** — `uv run pytest packages/agentbox-api/tests/test_provider_model_admin.py -q`.

- [ ] **Step 3: Implement in `routers/providers.py`**

Add `Agent` to the core import and:
```python
class ProviderUpdate(BaseModel):
    name: str | None = None
    kind: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    models_url: str | None = None


@router.put("/{pid}", response_model=ProviderRead)
async def update_provider(
    pid: str,
    body: ProviderUpdate,
    request: Request,
    _=Depends(require_permission("providers:create")),
):
    async with request.app.state.session_factory() as s:
        provider = (await s.execute(select(Provider).where(Provider.id == pid))).scalars().first()
        if provider is None:
            raise HTTPException(status_code=404, detail="Not found")
        for field in ("name", "kind", "base_url", "api_key", "models_url"):
            value = getattr(body, field)
            if value is not None:
                setattr(provider, field, value)
        s.add(provider)
        await s.commit()
        await s.refresh(provider)
    return provider
```
Replace `delete_provider`:
```python
@router.delete("/{pid}")
async def delete_provider(
    pid: str, request: Request, _=Depends(require_permission("providers:delete"))
):
    async with request.app.state.session_factory() as s:
        provider = (await s.execute(select(Provider).where(Provider.id == pid))).scalars().first()
        if provider is None:
            raise HTTPException(status_code=404, detail="Not found")
        models = (await s.execute(select(Model).where(Model.provider_id == pid))).scalars().all()
        model_ids = [m.id for m in models]
        if model_ids:
            in_use = (
                await s.execute(select(Agent).where(Agent.model_id.in_(model_ids)))  # ty: ignore[missing-attribute]
            ).scalars().first()
            if in_use is not None:
                raise HTTPException(status_code=409, detail="Model in use")
        for model in models:
            await s.delete(model)
        await s.delete(provider)
        await s.commit()
    return {"ok": True}
```

- [ ] **Step 4: Run tests + lint + commit** — `uv run pytest ... -q` → pass; `uv run ruff check packages/agentbox-api` → clean.
```bash
git add packages/agentbox-api/src/agentbox_api/routers/providers.py packages/agentbox-api/tests/test_provider_model_admin.py
git commit -m "feat(api): provider update + safe provider delete"
```

---

### Task 2: Backend — model create/delete

**Files:** `routers/models.py`; extend `tests/test_provider_model_admin.py`.

- [ ] **Step 1: Write failing tests**

```python
async def test_model_create_duplicate_and_delete():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        r = await client.post("/models", json={"provider_id": "prov", "name": "m2"}, headers=h)
        assert r.status_code == 200
        mid = r.json()["id"]
        dup = await client.post("/models", json={"provider_id": "prov", "name": "m2"}, headers=h)
        assert dup.status_code == 409
        assert (await client.delete(f"/models/{mid}", headers=h)).status_code == 200
    finally:
        await client.aclose()
        await engine.dispose()


async def test_model_delete_blocked_when_in_use():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        async with factory() as s:
            s.add(Agent(id="ag", name="a", description="", instructions="", model_id="m1"))
            await s.commit()
        r = await client.delete("/models/m1", headers=h)
        assert r.status_code == 409
    finally:
        await client.aclose()
        await engine.dispose()
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement in `routers/models.py`**

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_models.tables.core import Agent, Model, Provider


class ModelCreate(BaseModel):
    provider_id: str
    name: str


@router.post("", response_model=Model)
async def create_model(
    body: ModelCreate, request: Request, _=Depends(require_permission("providers:create"))
):
    async with request.app.state.session_factory() as s:
        provider = (await s.execute(select(Provider).where(Provider.id == body.provider_id))).scalars().first()
        if provider is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        dup = (
            await s.execute(
                select(Model).where(Model.provider_id == body.provider_id, Model.name == body.name)
            )
        ).scalars().first()
        if dup is not None:
            raise HTTPException(status_code=409, detail="Model already exists")
        model = Model(id=uuid.uuid4().hex, provider_id=body.provider_id, name=body.name)
        s.add(model)
        await s.commit()
        await s.refresh(model)
    return model


@router.delete("/{mid}")
async def delete_model(
    mid: str, request: Request, _=Depends(require_permission("providers:create"))
):
    async with request.app.state.session_factory() as s:
        model = (await s.execute(select(Model).where(Model.id == mid))).scalars().first()
        if model is None:
            raise HTTPException(status_code=404, detail="Not found")
        in_use = (await s.execute(select(Agent).where(Agent.model_id == mid))).scalars().first()
        if in_use is not None:
            raise HTTPException(status_code=409, detail="Model in use")
        await s.delete(model)
        await s.commit()
    return {"ok": True}
```
(Keep `list_models_endpoint`.)

- [ ] **Step 4: Run tests + lint + commit.**
```bash
git add packages/agentbox-api/src/agentbox_api/routers/models.py packages/agentbox-api/tests/test_provider_model_admin.py
git commit -m "feat(api): model create/delete with in-use guard"
```

---

### Task 3: Backend — session delete + shared helper + schema regen

**Files:** `runtime.py`, `routers/sessions.py`, `acp_server.py`; create/extend tests.

- [ ] **Step 1: Write failing test**

Create `tests/test_session_delete.py`:
```python
import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import Permission, Role, RolePermissionLink, User, UserRoleLink
from agentbox_models.tables.core import Agent, Model, Project, Provider, SessionAttachment, SessionRow, TurnRow


async def test_session_delete_removes_everything():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw")))
        s.add(Role(id="r1", name="role"))
        s.add(Permission(id="p0", name="sessions:create"))
        s.add(RolePermissionLink(role_id="r1", permission_id="p0"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(Provider(id="prov", name="test", kind="test"))
        s.add(Model(id="m", provider_id="prov", name="mm"))
        s.add(Agent(id="ag", name="a", description="", instructions="", model_id="m"))
        s.add(Project(id="prj", name="p", path=".", owner_id="u1"))
        s.add(SessionRow(id="s1", project_id="prj", agent_id="ag"))
        s.add(TurnRow(id="t1", session_id="s1", role="user", content="hi"))
        s.add(SessionAttachment(id="a1", session_id="s1", media_type="text/plain", filename="f", data=b"x"))
        await s.commit()
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        token = (await client.post("/auth/login", json={"username": "alice", "password": "pw"})).json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        assert (await client.delete("/sessions/s1", headers=h)).status_code == 200
        async with factory() as s:
            assert await s.get(SessionRow, "s1") is None
            assert await s.get(TurnRow, "t1") is None
            assert await s.get(SessionAttachment, "a1") is None
    finally:
        await client.aclose()
        await engine.dispose()
```

- [ ] **Step 2: Implement `delete_session_data` in `runtime.py`**

Add imports `SessionAttachment, SessionRow, TurnRow` and:
```python
async def delete_session_data(factory, session_id: str) -> None:
    async with factory() as s:
        for turn in (await s.execute(select(TurnRow).where(TurnRow.session_id == session_id))).scalars().all():
            await s.delete(turn)
        for attachment in (
            await s.execute(select(SessionAttachment).where(SessionAttachment.session_id == session_id))
        ).scalars().all():
            await s.delete(attachment)
        row = (await s.execute(select(SessionRow).where(SessionRow.id == session_id))).scalars().first()
        if row is not None:
            await s.delete(row)
        await s.commit()
```

- [ ] **Step 3: Add `DELETE /sessions/{sid}`**

In `routers/sessions.py`, import `delete_session_data` and:
```python
@router.delete("/{sid}")
async def delete_session(
    sid: str, request: Request, _=Depends(require_permission("sessions:create"))
):
    factory = request.app.state.session_factory
    async with factory() as s:
        row = (await s.execute(select(SessionRow).where(SessionRow.id == sid))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    await delete_session_data(factory, sid)
    return {"ok": True}
```

- [ ] **Step 4: Reuse the helper in ACP**

In `acp_server.py`, import `delete_session_data` and replace the inline body of `delete_session`:
```python
    async def delete_session(self, session_id, **kwargs):
        await delete_session_data(self._factory, session_id)
        self._sessions.pop(session_id, None)
        return s.DeleteSessionResponse()
```
Remove now-unused `SessionAttachment` import if flagged.

- [ ] **Step 5: Run tests, regen schema, commit**

Run: `uv run pytest packages/agentbox-api/tests -q` → all pass.
```bash
uv run python -c "import json; from agentbox_api.app import create_app; from agentbox_api.config import Settings; open('apps/web/openapi.json','w',encoding='utf-8').write(json.dumps(create_app(Settings(jwt_secret='x'*32)).openapi(), indent=2))"
```
```powershell
Set-Location apps/web; bun run codegen
```
```bash
git add packages/agentbox-api/src/agentbox_api/runtime.py packages/agentbox-api/src/agentbox_api/routers/sessions.py packages/agentbox-api/src/agentbox_api/acp_server.py packages/agentbox-api/tests/test_session_delete.py apps/web/openapi.json apps/web/src/api/schema.d.ts
git commit -m "feat(api): session delete + shared cleanup helper"
```

---

### Task 4: Frontend — API helpers + hooks

**Files:** `apps/web/src/api/endpoints.ts`, `queries.ts`.

- [ ] **Step 1: Add endpoints**

```ts
export async function updateProvider(
  pid: string,
  body: { name?: string; kind?: string; base_url?: string; api_key?: string; models_url?: string },
): Promise<Provider> {
  const { data, error } = await api.PUT("/providers/{pid}", { params: { path: { pid } }, body });
  if (error) throw new Error("Failed to update provider");
  return data as Provider;
}
export async function createModel(body: { provider_id: string; name: string }): Promise<Model> {
  const { data, error } = await api.POST("/models", { body });
  if (error) throw new Error("Failed to create model");
  return data as Model;
}
export async function deleteModel(mid: string): Promise<void> {
  await api.DELETE("/models/{mid}", { params: { path: { mid } } });
}
export async function deleteSession(sid: string): Promise<void> {
  await api.DELETE("/sessions/{sid}", { params: { path: { sid } } });
}
```

- [ ] **Step 2: Add hooks** (invalidate `providers`, `models`, `sessions`):
```ts
export function useUpdateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ pid, body }: { pid: string; body: Parameters<typeof updateProvider>[1] }) =>
      updateProvider(pid, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers"] }),
  });
}
export function useCreateModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createModel,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["models"] }),
  });
}
export function useDeleteModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteModel,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["models"] }),
  });
}
export function useDeleteSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteSession,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
}
```

- [ ] **Step 3: Build + commit** — `Set-Location apps/web; bun run build`.
```bash
git add apps/web/src/api/endpoints.ts apps/web/src/api/queries.ts
git commit -m "feat(web): provider/model/session API helpers + hooks"
```

---

### Task 5: Frontend — Providers tabs (edit + models)

**Files:** `apps/web/src/pages/ProvidersPage.tsx`; create `ProvidersPage.test.tsx`.

- [ ] **Step 1: Write failing test**

```tsx
import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("../api/queries", () => ({
  useProviders: () => ({ data: [{ id: "p1", name: "prov", kind: "generic" }] }),
  useModels: () => ({ data: [{ id: "m1", provider_id: "p1", name: "m" }] }),
  useCreateProvider: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteProvider: () => ({ mutate: vi.fn() }),
  useRefreshModels: () => ({ mutateAsync: vi.fn() }),
  useUpdateProvider: () => ({ mutateAsync: vi.fn() }),
  useCreateModel: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteModel: () => ({ mutateAsync: vi.fn() }),
}));

import { ProvidersPage } from "./ProvidersPage";

test("renders Providers and Models tabs", () => {
  render(
    <MantineProvider>
      <ProvidersPage />
    </MantineProvider>,
  );
  expect(screen.getByRole("tab", { name: "Providers" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Models" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Implement tabs + edit modal + models tab**

Replace the page body with:
```tsx
export function ProvidersPage() {
  return (
    <div>
      <h1 className="title">Providers</h1>
      <Tabs defaultValue="providers">
        <Tabs.List>
          <Tabs.Tab value="providers">Providers</Tabs.Tab>
          <Tabs.Tab value="models">Models</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="providers" pt="md"><ProvidersTab /></Tabs.Panel>
        <Tabs.Panel value="models" pt="md"><ModelsTab /></Tabs.Panel>
      </Tabs>
    </div>
  );
}

function ProvidersTab() {
  // existing create form + table + Refresh/Delete; add an Edit button per row:
  // <Button size="xs" onClick={() => setEditing(p)}>Edit</Button>
  // {editing && <ProviderEditModal provider={editing} onClose={() => setEditing(null)} />}
}

function ProviderEditModal({ provider, onClose }: { provider: Provider; onClose: () => void }) {
  const update = useUpdateProvider();
  const [name, setName] = useState(provider.name);
  const [kind, setKind] = useState(provider.kind);
  const [baseUrl, setBaseUrl] = useState(provider.base_url ?? "");
  const [apiKey, setApiKey] = useState("");
  const [modelsUrl, setModelsUrl] = useState(provider.models_url ?? "");
  async function onSave() {
    await update.mutateAsync({
      pid: provider.id,
      body: { name, kind, base_url: baseUrl, models_url: modelsUrl, ...(apiKey ? { api_key: apiKey } : {}) },
    });
    onClose();
  }
  return (
    <Modal opened onClose={onClose} title="Edit provider">
      <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
      <TextInput label="Kind" value={kind} onChange={(e) => setKind(e.currentTarget.value)} />
      <TextInput label="Base URL" value={baseUrl} onChange={(e) => setBaseUrl(e.currentTarget.value)} />
      <TextInput label="API key" placeholder="leave blank to keep" value={apiKey} onChange={(e) => setApiKey(e.currentTarget.value)} />
      <TextInput label="Models URL" value={modelsUrl} onChange={(e) => setModelsUrl(e.currentTarget.value)} />
      <Button mt="md" onClick={onSave}>Save</Button>
    </Modal>
  );
}

function ModelsTab() {
  const { data: models } = useModels();
  const { data: providers } = useProviders();
  const create = useCreateModel();
  const del = useDeleteModel();
  const [providerId, setProviderId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const providerName = (id: string) => providers?.find((p) => p.id === id)?.name ?? id;
  async function onCreate() {
    if (!providerId || !name) return;
    await create.mutateAsync({ provider_id: providerId, name });
    setName("");
  }
  return (
    <div>
      <div className="box">
        <Select label="Provider" data={(providers ?? []).map((p) => ({ value: p.id, label: p.name }))} value={providerId} onChange={setProviderId} />
        <TextInput label="Model name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
        <Button mt="md" onClick={onCreate} loading={create.isPending}>Create model</Button>
      </div>
      <Table>
        <Table.Thead><Table.Tr><Table.Th>Provider</Table.Th><Table.Th>Name</Table.Th><Table.Th>Actions</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {(models ?? []).map((m) => (
            <Table.Tr key={m.id}>
              <Table.Td>{providerName(m.provider_id)}</Table.Td>
              <Table.Td>{m.name}</Table.Td>
              <Table.Td><Button size="xs" color="red" onClick={() => del.mutateAsync(m.id)}>Delete</Button></Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}
```

- [ ] **Step 3: Run tests + build + commit**
```powershell
Set-Location apps/web; bun run test ProvidersPage; bun run build
```
```bash
git add apps/web/src/pages/ProvidersPage.tsx apps/web/src/pages/ProvidersPage.test.tsx
git commit -m "feat(web): provider tabs (edit + model management)"
```

---

### Task 6: Frontend — project tree session delete

**Files:** `apps/web/src/components/projects/ProjectTree.tsx`; extend `ProjectTree.test.tsx`.

- [ ] **Step 1: Write failing test**

Add to `ProjectTree.test.tsx` (mock queries + `modals`):
```tsx
import { MantineProvider } from "@mantine/core";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

vi.mock("@mantine/modals", () => ({
  modals: { openConfirmModal: (opts: { onConfirm: () => void }) => opts.onConfirm() },
}));
vi.mock("../../api/queries", () => ({
  useProjects: () => ({ data: [{ id: "prj", name: "P" }], isLoading: false, error: null }),
  useSessions: () => ({ data: [{ id: "s1", project_id: "prj", created_at: "x" }] }),
  useDeleteProject: () => ({ mutate: vi.fn() }),
  useDeleteSession: () => ({ mutateAsync: vi.fn() }),
}));
vi.mock("./NewProjectModal", () => ({ NewProjectModal: () => null }));
vi.mock("./NewSessionModal", () => ({ NewSessionModal: () => null }));

import { ProjectTree } from "./ProjectTree";

test("deletes a session", () => {
  render(
    <MantineProvider>
      <MemoryRouter>
        <ProjectTree />
      </MemoryRouter>
    </MantineProvider>,
  );
  fireEvent.click(screen.getByLabelText("Delete session s1"));
  // the mocked confirm modal invokes onConfirm immediately
});
```

- [ ] **Step 2: Implement**

Use `useDeleteSession`, `useLocation`, `useNavigate`, `modals`. Render each session with a delete button whose `aria-label` is `Delete session ${s.id}`, opening a confirm modal that calls `deleteSession.mutateAsync(id)` and, if `location.pathname === "/sessions/" + id`, navigates `/`.
```tsx
function onDeleteSession(id: string) {
  modals.openConfirmModal({
    title: "Delete session?",
    labels: { confirm: "Delete", cancel: "Cancel" },
    confirmProps: { color: "red" },
    onConfirm: async () => {
      await deleteSession.mutateAsync(id);
      if (location.pathname === `/sessions/${id}`) navigate("/");
    },
  });
}
// in the session row:
<button type="button" aria-label={`Delete session ${s.id}`} onClick={() => onDeleteSession(s.id)}>×</button>
```

- [ ] **Step 3: Run tests + build + commit.**
```bash
git add apps/web/src/components/projects/ProjectTree.tsx apps/web/src/components/projects/ProjectTree.test.tsx
git commit -m "feat(web): delete sessions from the project tree"
```

---

### Task 7: E2E — provider/model management + session delete

**Files:** create `apps/web/e2e/provider-model-admin.spec.ts`.

- [ ] **Step 1: Write the spec**

```ts
import { expect, test } from "@playwright/test";

const API = "http://localhost:8000";

test("manage providers/models and delete a session", async ({ page, request }) => {
  const suffix = Date.now();
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  await page.getByRole("link", { name: "Providers" }).click();
  await page.getByLabel("Name").fill(`e2e-prov-${suffix}`);
  await page.getByLabel("Models URL").fill("http://localhost:9999/models");
  await page.getByRole("button", { name: "Create provider" }).click();

  const row = page.getByRole("row", { name: new RegExp(`e2e-prov-${suffix}`) });
  await row.getByRole("button", { name: "Refresh models" }).click();

  // Edit provider name.
  await row.getByRole("button", { name: "Edit" }).click();
  const modal = page.getByRole("dialog");
  await modal.getByLabel("Name").fill(`e2e-prov-edit-${suffix}`);
  await modal.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("cell", { name: `e2e-prov-edit-${suffix}` })).toBeVisible();

  // Models tab: add + delete a model.
  await page.getByRole("tab", { name: "Models" }).click();
  await page.getByRole("combobox", { name: "Provider" }).click();
  await page.getByRole("option", { name: `e2e-prov-edit-${suffix}` }).click();
  await page.getByLabel("Model name").fill(`e2e-model-${suffix}`);
  await page.getByRole("button", { name: "Create model" }).click();
  await expect(page.getByRole("cell", { name: `e2e-model-${suffix}` })).toBeVisible();

  // Session delete: create a project+session via the API, then delete it in the tree.
  const raw = await page.evaluate(() => sessionStorage.getItem("agentbox-auth"));
  const token = JSON.parse(raw as string).state.token as string;
  const h = { Authorization: `Bearer ${token}` };
  const prov = await request.get(`${API}/providers`, { headers: h });
  const provId = (await prov.json()).find((p: { name: string }) => p.name === `e2e-prov-edit-${suffix}`).id;
  const proj = await request.post(`${API}/projects`, { headers: h, data: { name: `e2e-proj-${suffix}`, path: "." } });
  const projId = (await proj.json()).id;
  const agent = await request.post(`${API}/agents`, { headers: h, data: { name: `e2e-agent-${suffix}`, model: "e2e-model", tool_bindings: [] } });
  if (agent.status() !== 200) {
    // ensure a model exists for the agent
    await request.post(`${API}/models`, { headers: h, data: { provider_id: provId, name: "e2e-model" } });
    await request.post(`${API}/agents`, { headers: h, data: { name: `e2e-agent-${suffix}`, model: "e2e-model", tool_bindings: [] } });
  }
  const sess = await request.post(`${API}/sessions`, { headers: h, data: { project_id: projId, agent_id: `e2e-agent-${suffix}` } });
  const sessionId = (await sess.json()).id;

  await page.reload();
  await page.getByRole("link", { name: "Session 1" }).first().click();
  await page.getByLabel(`Delete session ${sessionId}`).click();
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByRole("link", { name: "Session 1" })).toHaveCount(0);
});
```

> The exact model/agent seeding may need adjustment based on the stub server's model name; keep the API fallback.

- [ ] **Step 2: Run + commit.**
```powershell
Set-Location apps/web; bun run e2e
```
```bash
git add apps/web/e2e/provider-model-admin.spec.ts
git commit -m "test(web): E2E provider/model management + session delete"
```

---

## Notes

- `providers:delete` guard already exists; the new cascade/409 lives in `delete_provider`.
- Regenerate `schema.d.ts` after the backend changes (Task 3).
- For the session-delete confirm modal in tests, mock `@mantine/modals` `openConfirmModal` to run `onConfirm` immediately.
