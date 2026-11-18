# Agents + Providers Management UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build provider/agent management pages in `apps/web`, backed by hardened endpoints (CORS, dev seed, server ids, secret-safe provider reads, model persistence), and prove the flows with **Playwright E2E on the real stack**.

**Architecture:** Backend gains CORS, a dev server that seeds an admin, server-generated ids, `ProviderRead` (no api_key), model refresh (persist) + `GET /models`. Frontend adds endpoints/hooks, a Providers page, and an Agents page with a full create form. Playwright starts a stub models server + the seeded backend + Vite, then drives the browser through the management flow.

**Tech Stack:** FastAPI, pytest; React/TS, TanStack Query, Mantine; Playwright (`@playwright/test`); Bun.

## Global Constraints

- Backend: `ruff`/`ty`/`bandit` clean; per-package `uv run pytest` green (`cd packages/agentbox-api`).
- Frontend: `bun run build` green. **Functional validation is via Playwright E2E**, not heavy mocks.
- No secrets in responses (`ProviderRead` omits `api_key`).
- Regenerate `apps/web/openapi.json` + `schema.d.ts` after backend changes.

---

### Task 1: Backend CORS + dev server + admin seed

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/config.py`
- Modify: `packages/agentbox-api/src/agentbox_api/app.py`
- Create: `packages/agentbox-api/src/agentbox_api/dev_seed.py`
- Create: `packages/agentbox-api/src/agentbox_api/dev_server.py`
- Test: `packages/agentbox-api/tests/test_dev.py`

**Interfaces:**
- Produces: `Settings.cors_origins`; CORS on the app; `seed_admin(factory)`; `python -m agentbox_api.dev_server` (seeded uvicorn).

- [ ] **Step 1: Config + CORS**

```python
# config.py — add field
cors_origins: list[str] = ["http://localhost:5173"]
```

```python
# app.py — add import + middleware (before include_router)
from fastapi.middleware.cors import CORSMiddleware
...
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

- [ ] **Step 2: Write the failing seed + CORS test**

```python
# tests/test_dev.py
import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.dev_seed import seed_admin
from agentbox_api.security import verify_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import User
from sqlmodel import select


async def test_cors_allows_frontend_origin():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/openapi.json", headers={"Origin": "http://localhost:5173"})
        assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    await engine.dispose()


async def test_seed_admin_idempotent():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    await seed_admin(factory)
    await seed_admin(factory)
    async with factory() as s:
        users = (await s.execute(select(User).where(User.username == "admin"))).scalars().all()
        assert len(users) == 1
        assert verify_password("admin", users[0].password_hash)
    await engine.dispose()
```

- [ ] **Step 3: Run to fail** → `ModuleNotFoundError` / missing CORS header.

- [ ] **Step 4: Implement seed + dev server**

```python
# dev_seed.py
import uuid

from sqlmodel import select

from agentbox_api.security import hash_password
from agentbox_models.tables.auth import (
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)

ALL_PERMISSIONS = [
    "agents:create", "agents:read", "agents:delete",
    "providers:create", "providers:read", "providers:delete", "providers:list-models",
    "projects:create", "projects:read", "projects:delete",
    "sessions:create", "sessions:read",
    "users:manage", "roles:manage", "api_keys:manage",
]


async def seed_admin(factory) -> None:
    async with factory() as s:
        existing = (
            await s.execute(select(User).where(User.username == "admin"))
        ).scalars().first()
        if existing is not None:
            return
        uid = uuid.uuid4().hex
        rid = uuid.uuid4().hex
        s.add(
            User(
                id=uid,
                username="admin",
                email="admin@example.com",
                password_hash=hash_password("admin"),
            )
        )
        s.add(Role(id=rid, name="admin"))
        for name in ALL_PERMISSIONS:
            pid = uuid.uuid4().hex
            s.add(Permission(id=pid, name=name))
            s.add(RolePermissionLink(role_id=rid, permission_id=pid))
        s.add(UserRoleLink(user_id=uid, role_id=rid))
        await s.commit()
```

```python
# dev_server.py
import asyncio
import os

import uvicorn

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.dev_seed import seed_admin
from agentbox_models.db import create_engine_and_sessionmaker, init_db


def main() -> None:
    settings = Settings()
    engine, factory = create_engine_and_sessionmaker(settings.database_url)
    asyncio.run(init_db(engine))
    asyncio.run(seed_admin(factory))
    app = create_app(settings, engine=engine, session_factory=factory)
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run to pass + checks**

Run: `uv run pytest tests/test_dev.py -q` → PASS. `uv run ruff check`, `uv run ty check packages`, `uv run bandit -r packages/agentbox-api/src` → clean.

- [ ] **Step 6: Commit**

```bash
git add packages/agentbox-api
git commit -m "feat(api): CORS + dev server with admin seed"
```

---

### Task 2: Backend provider hardening + models persistence

**Files:**
- Modify: `packages/agentbox-models/src/agentbox_models/repos/crud.py` (add `ModelRepository`)
- Modify: `packages/agentbox-api/src/agentbox_api/routers/providers.py`
- Create: `packages/agentbox-api/src/agentbox_api/routers/models.py`
- Modify: `packages/agentbox-api/src/agentbox_api/app.py` (register models router)
- Test: `packages/agentbox-api/tests/test_management.py`
- Regenerate: `apps/web/openapi.json`, `apps/web/src/api/schema.d.ts`

**Interfaces:**
- Produces: `POST /providers {name,kind,base_url?,api_key?,models_url?} -> ProviderRead`; `GET /providers -> list[ProviderRead]`; `POST /providers/{pid}/models/refresh -> list[Model]`; `GET /models -> list[Model]`.

- [ ] **Step 1: Add ModelRepository**

```python
# crud.py — add import Model and class
from agentbox_models.tables.core import Model  # add to the core imports

class ModelRepository(Repository[Model]):
    model = Model
```

- [ ] **Step 2: Write the failing test** (mock `list_models`)

```python
# tests/test_management.py
import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings

from tests.test_crud_routers import _make_app, _login  # reuse helpers


async def test_provider_read_omits_api_key():
    engine, client = await _make_app(["providers:create", "providers:read"])
    try:
        token = await _login(client)
        h = {"Authorization": f"Bearer {token}"}
        r = await client.post(
            "/providers",
            json={"name": "openai", "kind": "generic", "api_key": "sk-secret"},
            headers=h,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["id"]
        assert "api_key" not in body
        r = await client.get("/providers", headers=h)
        assert all("api_key" not in p for p in r.json())
    finally:
        await client.aclose()
        await engine.dispose()


async def test_refresh_persists_and_dedupes(monkeypatch):
    monkeypatch.setattr(
        "agentbox_api.routers.providers.list_models", lambda provider: _async(["m1", "m2"])
    )
    engine, client = await _make_app(
        ["providers:create", "providers:read", "providers:list-models"]
    )
    try:
        token = await _login(client)
        h = {"Authorization": f"Bearer {token}"}
        r = await client.post(
            "/providers", json={"name": "p", "kind": "generic", "models_url": "http://x"}, headers=h
        )
        pid = r.json()["id"]
        r = await client.post(f"/providers/{pid}/models/refresh", headers=h)
        assert {m["name"] for m in r.json()} == {"m1", "m2"}
        r = await client.post(f"/providers/{pid}/models/refresh", headers=h)
        assert len(r.json()) == 2  # no duplicates
        r = await client.get("/models", headers=h)
        assert len(r.json()) == 2
    finally:
        await client.aclose()
        await engine.dispose()


async def _async(value):
    return value
```

(Ensure helpers `_make_app`/`_login` are importable — they live in `tests/test_crud_routers.py`; if import is awkward, copy them into this file.)

- [ ] **Step 3: Run to fail.**

- [ ] **Step 4: Implement providers router**

```python
# providers.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_models.repos.crud import ProviderRepository
from agentbox_models.tables.core import Model, Provider
from agentbox_providers.models import list_models

router = APIRouter(prefix="/providers", tags=["providers"])


class ProviderCreate(BaseModel):
    name: str
    kind: str
    base_url: str | None = None
    api_key: str | None = None
    models_url: str | None = None


class ProviderRead(BaseModel):
    id: str
    name: str
    kind: str
    base_url: str | None = None
    models_url: str | None = None
    is_builtin: bool = False


@router.post("", response_model=ProviderRead)
async def create_provider(
    body: ProviderCreate, request: Request, _=Depends(require_permission("providers:create"))
):
    return await ProviderRepository(request.app.state.session_factory).create(
        Provider(id=uuid.uuid4().hex, **body.model_dump())
    )


@router.get("", response_model=list[ProviderRead])
async def list_providers(request: Request, _=Depends(require_permission("providers:read"))):
    return await ProviderRepository(request.app.state.session_factory).list()


@router.post("/{pid}/models/refresh", response_model=list[Model])
async def refresh_models(
    pid: str, request: Request, _=Depends(require_permission("providers:list-models"))
):
    factory = request.app.state.session_factory
    provider = await ProviderRepository(factory).get(pid)
    if provider is None:
        raise HTTPException(status_code=404, detail="Not found")
    names = await list_models(provider)
    async with factory() as s:
        existing = (
            await s.execute(select(Model).where(Model.provider_id == pid))
        ).scalars().all()
        have = {m.name for m in existing}
        for name in names:
            if name not in have:
                s.add(Model(id=uuid.uuid4().hex, provider_id=pid, name=name))
        await s.commit()
        rows = (
            await s.execute(select(Model).where(Model.provider_id == pid))
        ).scalars().all()
    return rows


@router.delete("/{pid}")
async def delete_provider(
    pid: str, request: Request, _=Depends(require_permission("providers:delete"))
):
    await ProviderRepository(request.app.state.session_factory).delete(pid)
    return {"ok": True}
```

```python
# routers/models.py
from fastapi import APIRouter, Depends, Request

from agentbox_api.deps import require_permission
from agentbox_models.repos.crud import ModelRepository
from agentbox_models.tables.core import Model

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[Model])
async def list_models_endpoint(
    request: Request, _=Depends(require_permission("providers:read"))
):
    return await ModelRepository(request.app.state.session_factory).list()
```

Register in `app.py`: `from agentbox_api.routers.models import router as models_router` + `app.include_router(models_router)`.

- [ ] **Step 5: Run tests + checks.**

- [ ] **Step 6: Regenerate schema** (`uv run python apps/web/scripts/gen-openapi.py`; `cd apps/web && bun run codegen`).

- [ ] **Step 7: Commit**

```bash
git add packages/agentbox-models packages/agentbox-api apps/web/openapi.json apps/web/src/api/schema.d.ts
git commit -m "feat(api): provider hardening + models refresh/list"
```

---

### Task 3: Frontend endpoints + hooks

**Files:**
- Modify: `apps/web/src/api/endpoints.ts`
- Modify: `apps/web/src/api/queries.ts`

**Interfaces:**
- Produces: `Provider`, `Model` types; `fetchProviders/createProvider/deleteProvider/refreshModels/fetchModels/createAgent/deleteAgent`; hooks `useProviders/useModels/useCreateProvider/useDeleteProvider/useRefreshModels/useCreateAgent/useDeleteAgent`.

- [ ] **Step 1: Extend endpoints**

```ts
// endpoints.ts — add
export type Provider = components["schemas"]["ProviderRead"];
export type Model = components["schemas"]["Model"];

export async function fetchProviders(): Promise<Provider[]> {
  const { data } = await api.GET("/providers");
  return data ?? [];
}
export async function createProvider(body: {
  name: string;
  kind: string;
  base_url?: string;
  api_key?: string;
  models_url?: string;
}): Promise<Provider> {
  const { data, error } = await api.POST("/providers", { body });
  if (error) throw new Error("Failed to create provider");
  return data as Provider;
}
export async function deleteProvider(id: string): Promise<void> {
  await api.DELETE("/providers/{pid}", { params: { path: { pid: id } } });
}
export async function refreshModels(id: string): Promise<Model[]> {
  const { data } = await api.POST("/providers/{pid}/models/refresh", {
    params: { path: { pid: id } },
  });
  return data ?? [];
}
export async function fetchModels(): Promise<Model[]> {
  const { data } = await api.GET("/models");
  return data ?? [];
}
export async function createAgent(body: {
  name: string;
  description: string;
  instructions: string;
  model: string;
  tool_bindings: Record<string, unknown>[];
  mode_definitions: Record<string, unknown>[];
  sub_agent_ids: string[];
}): Promise<unknown> {
  const { data, error } = await api.POST("/agents", { body });
  if (error) throw new Error("Failed to create agent");
  return data;
}
export async function deleteAgent(name: string): Promise<void> {
  await api.DELETE("/agents/{name}", { params: { path: { name } } });
}
```

- [ ] **Step 2: Extend hooks**

```ts
// queries.ts — add
import { ..., createAgent, createProvider, deleteAgent, deleteProvider, fetchModels, fetchProviders, refreshModels } from "./endpoints";

export function useProviders() {
  return useQuery({ queryKey: ["providers"], queryFn: fetchProviders });
}
export function useModels() {
  return useQuery({ queryKey: ["models"], queryFn: fetchModels });
}
export function useCreateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createProvider,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers"] }),
  });
}
export function useDeleteProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteProvider,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers"] }),
  });
}
export function useRefreshModels() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: refreshModels,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["models"] }),
  });
}
export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createAgent,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}
export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteAgent,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}
```

- [ ] **Step 3: Build**

Run: `bun run build` → succeeds (types resolve from the regenerated schema).

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/api
git commit -m "feat(web): provider/model/agent endpoints + hooks"
```

---

### Task 4: Providers page

**Files:**
- Modify: `apps/web/src/pages/ProvidersPage.tsx`

**Interfaces:**
- Produces: a page listing providers, creating them, deleting, and refreshing models.

- [ ] **Step 1: Implement**

```tsx
// ProvidersPage.tsx
import { Button, Select, Table, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import {
  useCreateProvider,
  useDeleteProvider,
  useProviders,
  useRefreshModels,
} from "../api/queries";

export function ProvidersPage() {
  const { data: providers } = useProviders();
  const create = useCreateProvider();
  const del = useDeleteProvider();
  const refresh = useRefreshModels();
  const [name, setName] = useState("");
  const [kind, setKind] = useState<string | null>("generic");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [modelsUrl, setModelsUrl] = useState("");

  async function onCreate() {
    try {
      await create.mutateAsync({
        name,
        kind: kind ?? "generic",
        base_url: baseUrl || undefined,
        api_key: apiKey || undefined,
        models_url: modelsUrl || undefined,
      });
      setName("");
      setBaseUrl("");
      setApiKey("");
      setModelsUrl("");
    } catch {
      notifications.show({ message: "Failed to create provider", color: "red" });
    }
  }

  async function onRefresh(id: string) {
    try {
      const models = await refresh.mutateAsync(id);
      notifications.show({ message: `Refreshed ${models.length} models` });
    } catch {
      notifications.show({ message: "Failed to refresh models", color: "red" });
    }
  }

  return (
    <div>
      <h1 className="title">Providers</h1>
      <div className="box">
        <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
        <Select
          label="Kind"
          data={["generic", "openai_legacy", "openai_responses", "anthropic", "moonshot", "deepseek", "ollama"]}
          value={kind}
          onChange={setKind}
        />
        <TextInput label="Base URL" value={baseUrl} onChange={(e) => setBaseUrl(e.currentTarget.value)} />
        <TextInput label="API key" value={apiKey} onChange={(e) => setApiKey(e.currentTarget.value)} />
        <TextInput label="Models URL" value={modelsUrl} onChange={(e) => setModelsUrl(e.currentTarget.value)} />
        <Button mt="md" onClick={onCreate} loading={create.isPending}>
          Create provider
        </Button>
      </div>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Name</Table.Th>
            <Table.Th>Kind</Table.Th>
            <Table.Th>Actions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {(providers ?? []).map((p) => (
            <Table.Tr key={p.id}>
              <Table.Td>{p.name}</Table.Td>
              <Table.Td>{p.kind}</Table.Td>
              <Table.Td>
                <Button size="xs" onClick={() => onRefresh(p.id)}>
                  Refresh models
                </Button>
                <Button size="xs" color="red" ml="xs" onClick={() => del.mutate(p.id)}>
                  Delete
                </Button>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}
```

- [ ] **Step 2: Build** → `bun run build` succeeds.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/pages/ProvidersPage.tsx
git commit -m "feat(web): providers page (create/list/refresh/delete)"
```

---

### Task 5: Agents page (full create form)

**Files:**
- Modify: `apps/web/src/pages/AgentsPage.tsx`

**Interfaces:**
- Produces: a page listing agents, deleting them, and a full create form.

- [ ] **Step 1: Implement**

```tsx
// AgentsPage.tsx
import { Button, Checkbox, MultiSelect, Select, Table, Textarea, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import {
  useAgents,
  useCreateAgent,
  useDeleteAgent,
  useModels,
} from "../api/queries";

const NATIVE_TOOLS = ["read_text_file", "write_file", "list_directory"];

export function AgentsPage() {
  const { data: agents } = useAgents();
  const { data: models } = useModels();
  const create = useCreateAgent();
  const del = useDeleteAgent();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [model, setModel] = useState<string | null>(null);
  const [tools, setTools] = useState<string[]>([]);
  const [mcpServers, setMcpServers] = useState<string[]>([]);
  const [mcpInput, setMcpInput] = useState("");
  const [subAgents, setSubAgents] = useState<string[]>([]);
  const [modes, setModes] = useState<{ name: string; write: boolean }[]>([
    { name: "ask", write: false },
    { name: "agent", write: true },
  ]);

  async function onCreate() {
    if (!model) return;
    const tool_bindings = [
      ...tools.map((t) => ({ name: t })),
      ...mcpServers.map((url) => ({ server_url: url })),
    ];
    const mode_definitions = modes.map((m) => ({ name: m.name, flags: { write: m.write } }));
    try {
      await create.mutateAsync({
        name,
        description,
        instructions,
        model,
        tool_bindings,
        mode_definitions,
        sub_agent_ids: subAgents,
      });
      setName("");
      setDescription("");
      setInstructions("");
      setModel(null);
      setTools([]);
      setMcpServers([]);
      setSubAgents([]);
    } catch {
      notifications.show({ message: "Failed to create agent", color: "red" });
    }
  }

  return (
    <div>
      <h1 className="title">Agents</h1>
      <div className="box">
        <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
        <TextInput label="Description" value={description} onChange={(e) => setDescription(e.currentTarget.value)} />
        <Textarea label="Instructions" value={instructions} onChange={(e) => setInstructions(e.currentTarget.value)} />
        <Select
          label="Model"
          data={(models ?? []).map((m) => m.name)}
          value={model}
          onChange={setModel}
        />
        <div>
          <p className="label">Native tools</p>
          {NATIVE_TOOLS.map((t) => (
            <Checkbox
              key={t}
              label={t}
              checked={tools.includes(t)}
              onChange={(e) =>
                setTools((prev) =>
                  e.currentTarget.checked ? [...prev, t] : prev.filter((x) => x !== t),
                )
              }
            />
          ))}
        </div>
        <div>
          <p className="label">MCP servers</p>
          <TextInput
            placeholder="https://server/mcp"
            value={mcpInput}
            onChange={(e) => setMcpInput(e.currentTarget.value)}
          />
          <Button
            size="xs"
            onClick={() => {
              if (mcpInput) {
                setMcpServers((prev) => [...prev, mcpInput]);
                setMcpInput("");
              }
            }}
          >
            Add MCP server
          </Button>
          <ul>
            {mcpServers.map((u, i) => (
              <li key={i}>
                {u}{" "}
                <button type="button" onClick={() => setMcpServers((p) => p.filter((_, j) => j !== i))}>
                  ×
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="label">Modes</p>
          {modes.map((m, i) => (
            <div key={i}>
              <TextInput
                value={m.name}
                onChange={(e) =>
                  setModes((p) => p.map((x, j) => (j === i ? { ...x, name: e.currentTarget.value } : x)))
                }
              />
              <Checkbox
                label="Write enabled"
                checked={m.write}
                onChange={(e) =>
                  setModes((p) =>
                    p.map((x, j) => (j === i ? { ...x, write: e.currentTarget.checked } : x)),
                  )
                }
              />
            </div>
          ))}
        </div>
        <MultiSelect
          label="Sub-agents"
          data={(agents ?? []).map((a) => a.name)}
          value={subAgents}
          onChange={setSubAgents}
        />
        <Button mt="md" onClick={onCreate} loading={create.isPending}>
          Create agent
        </Button>
      </div>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Name</Table.Th>
            <Table.Th>Description</Table.Th>
            <Table.Th>Actions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {(agents ?? []).map((a) => (
            <Table.Tr key={a.name}>
              <Table.Td>{a.name}</Table.Td>
              <Table.Td>{a.description}</Table.Td>
              <Table.Td>
                <Button size="xs" color="red" onClick={() => del.mutate(a.name)}>
                  Delete
                </Button>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}
```

- [ ] **Step 2: Build** → `bun run build` succeeds.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/pages/AgentsPage.tsx
git commit -m "feat(web): agents page with full create form"
```

---

### Task 6: E2E (Playwright) — real-stack management flow

**Files:**
- Modify: `apps/web/package.json` (scripts + `@playwright/test` dev dep)
- Create: `apps/web/playwright.config.ts`
- Create: `apps/web/e2e/stub-server.ts`
- Create: `apps/web/e2e/management.spec.ts`
- Modify: `.gitignore` (test-results, playwright-report, e2e.db)

**Interfaces:**
- Produces: `bun run e2e` runs a real-stack management flow.

- [ ] **Step 1: Install Playwright**

Run (from `apps/web`): `bun add -d @playwright/test` then `bunx playwright install chromium`.

- [ ] **Step 2: Stub models server**

```ts
// e2e/stub-server.ts
const server = Bun.serve({
  port: 9999,
  fetch(req) {
    const url = new URL(req.url);
    if (url.pathname === "/models") {
      return Response.json({ object: "list", data: [{ id: "e2e-model" }] });
    }
    return new Response("not found", { status: 404 });
  },
});
console.log(`stub models server on ${server.port}`);
```

- [ ] **Step 3: Playwright config**

```ts
// playwright.config.ts
import path from "node:path";
import { defineConfig } from "@playwright/test";

const repoRoot = path.resolve(__dirname, "../..");

export default defineConfig({
  testDir: "./e2e",
  reporter: [["html", { open: "never" }]],
  use: { baseURL: "http://localhost:5173", trace: "on-first-retry" },
  webServer: [
    {
      command: "bun run e2e/stub-server.ts",
      url: "http://localhost:9999/models",
      reuseExistingServer: true,
    },
    {
      command: "uv run python -m agentbox_api.dev_server",
      cwd: repoRoot,
      url: "http://localhost:8000/openapi.json",
      reuseExistingServer: true,
      env: {
        DATABASE_URL: "sqlite+aiosqlite:///./e2e.db",
        JWT_SECRET: "e2e-secret-e2e-secret-e2e-secret-xx",
      },
    },
    {
      command: "bun run dev -- --port 5173",
      url: "http://localhost:5173",
      reuseExistingServer: true,
      env: { VITE_API_URL: "http://localhost:8000" },
    },
  ],
});
```

- [ ] **Step 4: The E2E test**

```ts
// e2e/management.spec.ts
import { test, expect } from "@playwright/test";

test("manage provider and agent end-to-end", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  // Provider
  await page.getByRole("link", { name: "Providers" }).click();
  await page.getByLabel("Name").fill("e2e-provider");
  await page.getByLabel("Kind").click();
  await page.getByRole("option", { name: "generic" }).click();
  await page.getByLabel("Models URL").fill("http://localhost:9999/models");
  await page.getByRole("button", { name: "Create provider" }).click();
  await expect(page.getByRole("cell", { name: "e2e-provider" })).toBeVisible();

  await page.getByRole("row", { name: /e2e-provider/ }).getByRole("button", { name: "Refresh models" }).click();

  // Agent
  await page.getByRole("link", { name: "Agents" }).click();
  await page.getByLabel("Name").fill("e2e-agent");
  await page.getByLabel("Model").click();
  await page.getByRole("option", { name: "e2e-model" }).click();
  await page.getByLabel("write_file").check();
  await page.getByRole("button", { name: "Create agent" }).click();
  await expect(page.getByRole("cell", { name: "e2e-agent" })).toBeVisible();

  await page.getByRole("row", { name: /e2e-agent/ }).getByRole("button", { name: "Delete" }).click();
  await expect(page.getByRole("cell", { name: "e2e-agent" })).toHaveCount(0);
});
```

- [ ] **Step 5: Scripts + gitignore**

```jsonc
// package.json — add
"e2e": "playwright test"
```

```gitignore
# .gitignore — add
test-results/
playwright-report/
e2e.db
```

- [ ] **Step 6: Run the E2E**

Run (from `apps/web`): `bun run e2e`
Expected: the management test passes (the browser drives the real stack). If Playwright/managed servers behave differently on this platform, adjust the config (ports, cwd, env) and re-run.

- [ ] **Step 7: Commit**

```bash
git add apps/web .gitignore
git commit -m "test(e2e): real-stack provider/agent management flow"
```

---

## Self-Review Notes

- **Spec coverage:** CORS/seed (1), provider+models backend (2), endpoints/hooks (3), providers page (4), agents page (5), Playwright E2E (6).
- **Extension points used:** FastAPI `CORSMiddleware`, `response_model`, uvicorn, Playwright `webServer`, Bun `serve`, Mantine inputs, TanStack Query.
- **Verification note:** the E2E is the primary functional proof; exact Mantine locators (labels/roles) and Playwright `webServer` behavior are validated by running the suite and adjusted as needed. Backend pytest covers the endpoint contracts (secret omission, refresh dedupe).
- **RoboHash avatars** remain future work (not in this sub-project).
