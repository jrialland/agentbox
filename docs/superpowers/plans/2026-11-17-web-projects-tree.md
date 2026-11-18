# Projects + Session Tree Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the left-hand project/session tree to `apps/web` (with New Project / New Session modals and a placeholder session page), backed by improved projects/sessions/agents endpoints (server-generated ids, owner-from-auth, typed responses).

**Architecture:** Backend create endpoints generate ids and derive the project owner from the authenticated user; CRUD responses become typed. The frontend adds thin `endpoints.ts` wrappers over the generated client, TanStack Query hooks (`queries.ts`), a sidebar `ProjectTree`, Mantine modals, and a `/sessions/:id` page.

**Tech Stack:** FastAPI (backend), pytest; React/TS, TanStack Query, Mantine, openapi-fetch, Vitest + Testing Library.

## Global Constraints

- Backend: `ruff`/`ty`/`bandit` clean; per-package `uv run pytest` green (`cd packages/agentbox-api`).
- Frontend: `bun run test` + `bun run build` green; tests mock the API layer (no real backend).
- Server owns ids and ownership: clients never send `id`/`owner_id`.
- Regenerate `apps/web/openapi.json` + `schema.d.ts` after backend changes.
- Session label = "Session N" (index per project by `created_at`).

---

### Task 1: Backend — server ids, owner-from-auth, typed responses

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/routers/projects.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/agents.py`
- Modify: `packages/agentbox-api/tests/test_crud_routers.py`
- Regenerate: `apps/web/openapi.json`, `apps/web/src/api/schema.d.ts`

**Interfaces:**
- Produces: `POST /projects {name, path} -> Project`; `POST /sessions {project_id, agent_id} -> SessionRow`; typed `GET /projects|/sessions|/agents`.

- [ ] **Step 1: Update the failing tests** (`test_crud_routers.py`) — use server-generated ids and assert ownership:

```python
async def test_projects_create_and_list():
    engine, client = await _make_app(["projects:create", "projects:read"])
    try:
        token = await _login(client)
        h = {"Authorization": f"Bearer {token}"}
        r = await client.post("/projects", json={"name": "myproj", "path": "/tmp/p"}, headers=h)
        assert r.status_code == 200
        created = r.json()
        assert created["id"]
        assert created["owner_id"] == "u1"
        r = await client.get("/projects", headers=h)
        assert any(p["id"] == created["id"] for p in r.json())
    finally:
        await client.aclose()
        await engine.dispose()


async def test_sessions_create_and_list():
    engine, client = await _make_app(["sessions:create", "sessions:read"])
    try:
        token = await _login(client)
        h = {"Authorization": f"Bearer {token}"}
        r = await client.post("/sessions", json={"project_id": "prj", "agent_id": "ag"}, headers=h)
        assert r.status_code == 200
        created = r.json()
        assert created["id"]
        r = await client.get("/sessions", headers=h)
        assert any(s["id"] == created["id"] for s in r.json())
    finally:
        await client.aclose()
        await engine.dispose()
```

- [ ] **Step 2: Run to fail** → `uv run pytest tests/test_crud_routers.py -q` (owner missing / id mismatch).

- [ ] **Step 3: Implement the projects router**

```python
# projects.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from agentbox_api.deps import require_permission
from agentbox_models.repos.crud import ProjectRepository
from agentbox_models.tables.core import Project

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    path: str


@router.post("", response_model=Project)
async def create_project(
    body: ProjectCreate, request: Request, _=Depends(require_permission("projects:create"))
):
    project = Project(
        id=uuid.uuid4().hex,
        name=body.name,
        path=body.path,
        owner_id=request.user.identity,
    )
    return await ProjectRepository(request.app.state.session_factory).create(project)


@router.get("", response_model=list[Project])
async def list_projects(request: Request, _=Depends(require_permission("projects:read"))):
    return await ProjectRepository(request.app.state.session_factory).list()


@router.get("/{pid}", response_model=Project)
async def get_project(pid: str, request: Request, _=Depends(require_permission("projects:read"))):
    p = await ProjectRepository(request.app.state.session_factory).get(pid)
    if p is None:
        raise HTTPException(status_code=404, detail="Not found")
    return p


@router.delete("/{pid}")
async def delete_project(
    pid: str, request: Request, _=Depends(require_permission("projects:delete"))
):
    await ProjectRepository(request.app.state.session_factory).delete(pid)
    return {"ok": True}
```

- [ ] **Step 4: Implement the sessions router create + typed list/get**

```python
# sessions.py (create + list/get parts; keep the chat endpoint unchanged)
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from agentbox_api.deps import require_permission
from agentbox_models.repos.crud import SessionRepository
from agentbox_models.tables.core import SessionRow

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    project_id: str
    agent_id: str


@router.post("", response_model=SessionRow)
async def create_session(
    body: SessionCreate, request: Request, _=Depends(require_permission("sessions:create"))
):
    session = SessionRow(
        id=uuid.uuid4().hex, project_id=body.project_id, agent_id=body.agent_id
    )
    return await SessionRepository(request.app.state.session_factory).create(session)


@router.get("", response_model=list[SessionRow])
async def list_sessions(request: Request, _=Depends(require_permission("sessions:read"))):
    return await SessionRepository(request.app.state.session_factory).list()


@router.get("/{sid}", response_model=SessionRow)
async def get_session(sid: str, request: Request, _=Depends(require_permission("sessions:read"))):
    s = await SessionRepository(request.app.state.session_factory).get(sid)
    if s is None:
        raise HTTPException(status_code=404, detail="Not found")
    return s
```

(Preserve `MessageRequest` + the `chat` endpoint and its imports exactly as they are.)

- [ ] **Step 5: Type the agents router** — add `response_model` and return specs:

```python
# agents.py — decorate and return spec instances instead of model_dump()
@router.post("", response_model=AgentSpec)
async def create_agent(...):
    repo = AgentRepository(request.app.state.session_factory)
    return await repo.save(_to_spec(body))

@router.get("", response_model=list[AgentSpec])
async def list_agents(...):
    repo = AgentRepository(request.app.state.session_factory)
    return await repo.list()

@router.get("/{name}", response_model=AgentSpec)
async def get_agent(...):
    repo = AgentRepository(request.app.state.session_factory)
    spec = await repo.load(name)
    if spec is None:
        raise HTTPException(status_code=404, detail="Not found")
    return spec
```

- [ ] **Step 6: Run tests + checks**

Run (from `packages/agentbox-api`): `uv run pytest -q` → green.
Run (repo root): `uv run ruff check`, `uv run ty check packages`, `uv run bandit -r packages/agentbox-api/src` → clean.

- [ ] **Step 7: Regenerate schema**

Run (repo root): `uv run python apps/web/scripts/gen-openapi.py`
Then (from `apps/web`): `bun run codegen`
Verify: `GET /projects` and `GET /agents` now have non-empty response schemas.

- [ ] **Step 8: Commit**

```bash
git add packages/agentbox-api apps/web/openapi.json apps/web/src/api/schema.d.ts
git commit -m "feat(api): server-generated ids + owner-from-auth; typed project/session/agent responses"
```

---

### Task 2: Frontend endpoints + query hooks

**Files:**
- Create: `apps/web/src/api/endpoints.ts`
- Create: `apps/web/src/api/queries.ts`
- Test: `apps/web/src/api/queries.test.tsx`

**Interfaces:**
- Produces: `fetchProjects/createProject/deleteProject/fetchSessions/createSession/fetchAgents`; hooks `useProjects/useSessions/useAgents/useCreateProject/useCreateSession/useDeleteProject`.

- [ ] **Step 1: Implement endpoints (thin wrappers over the typed client)**

```ts
// apps/web/src/api/endpoints.ts
import type { components } from "./schema";
import { api } from "./client";

export type Project = components["schemas"]["Project"];
export type Session = components["schemas"]["SessionRow"];
export type Agent = components["schemas"]["AgentSpec"];

export async function fetchProjects(): Promise<Project[]> {
  const { data } = await api.GET("/projects");
  return data ?? [];
}

export async function createProject(body: { name: string; path: string }): Promise<Project> {
  const { data, error } = await api.POST("/projects", { body });
  if (error) throw new Error("Failed to create project");
  return data as Project;
}

export async function deleteProject(id: string): Promise<void> {
  await api.DELETE("/projects/{pid}", { params: { path: { pid: id } } });
}

export async function fetchSessions(): Promise<Session[]> {
  const { data } = await api.GET("/sessions");
  return data ?? [];
}

export async function createSession(body: {
  project_id: string;
  agent_id: string;
}): Promise<Session> {
  const { data, error } = await api.POST("/sessions", { body });
  if (error) throw new Error("Failed to create session");
  return data as Session;
}

export async function fetchAgents(): Promise<Agent[]> {
  const { data } = await api.GET("/agents");
  return data ?? [];
}
```

- [ ] **Step 2: Implement hooks**

```ts
// apps/web/src/api/queries.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createProject,
  createSession,
  deleteProject,
  fetchAgents,
  fetchProjects,
  fetchSessions,
} from "./endpoints";

export function useProjects() {
  return useQuery({ queryKey: ["projects"], queryFn: fetchProjects });
}

export function useSessions() {
  return useQuery({ queryKey: ["sessions"], queryFn: fetchSessions });
}

export function useAgents() {
  return useQuery({ queryKey: ["agents"], queryFn: fetchAgents });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createProject,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}

export function useCreateSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createSession,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteProject,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}
```

- [ ] **Step 3: Write the hook test**

```tsx
// apps/web/src/api/queries.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import * as endpoints from "./endpoints";
import { useProjects } from "./queries";

test("useProjects returns fetched data", async () => {
  vi.spyOn(endpoints, "fetchProjects").mockResolvedValue([
    { id: "p1", name: "P", path: "/x", owner_id: "u1", created_at: "t" },
  ] as never);

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );

  const { result } = renderHook(() => useProjects(), { wrapper });
  await waitFor(() => expect(result.current.data?.length).toBe(1));
});
```

- [ ] **Step 4: Run test + build**

Run: `bun run test` (passes). `bun run build` (type-checks endpoints; requires Task 1's typed schema).

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/api
git commit -m "feat(web): add project/session/agent endpoints + query hooks"
```

---

### Task 3: Project tree + create modals

**Files:**
- Create: `apps/web/src/components/projects/NewProjectModal.tsx`
- Create: `apps/web/src/components/projects/NewSessionModal.tsx`
- Create: `apps/web/src/components/projects/ProjectTree.tsx`
- Modify: `apps/web/src/components/layout/AppShell.tsx` (render the tree in the sidebar)
- Test: `apps/web/src/components/projects/ProjectTree.test.tsx`

**Interfaces:**
- Produces: `ProjectTree` (projects + grouped sessions, create/delete actions, navigation).

- [ ] **Step 1: Write the failing test** (mock the endpoints)

```tsx
// apps/web/src/components/projects/ProjectTree.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

import * as endpoints from "../../api/endpoints";
import { ProjectTree } from "./ProjectTree";

function renderTree() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<ProjectTree />} />
          <Route path="/sessions/:id" element={<div>Session page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.spyOn(endpoints, "fetchProjects").mockResolvedValue([
    { id: "p1", name: "Proj A", path: "/a", owner_id: "u1", created_at: "t1" },
  ] as never);
  vi.spyOn(endpoints, "fetchSessions").mockResolvedValue([
    { id: "s1", project_id: "p1", agent_id: "ag", created_at: "t2" },
  ] as never);
  vi.spyOn(endpoints, "fetchAgents").mockResolvedValue([{ name: "coder" }] as never);
});

test("renders projects with grouped sessions and navigates", async () => {
  renderTree();
  expect(await screen.findByText("Proj A")).toBeInTheDocument();
  const session = await screen.findByText("Session 1");
  fireEvent.click(session);
  await waitFor(() => expect(screen.getByText("Session page")).toBeInTheDocument());
});

test("creates a project via the modal", async () => {
  const created = vi.spyOn(endpoints, "createProject").mockResolvedValue({
    id: "p2",
    name: "New",
    path: "/n",
    owner_id: "u1",
    created_at: "t",
  } as never);
  renderTree();
  fireEvent.click(screen.getByRole("button", { name: /new project/i }));
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "New" } });
  fireEvent.change(screen.getByLabelText("Path"), { target: { value: "/n" } });
  fireEvent.click(screen.getByRole("button", { name: /create/i }));
  await waitFor(() => expect(created).toHaveBeenCalledWith({ name: "New", path: "/n" }));
});
```

- [ ] **Step 2: Run to fail** → module missing.

- [ ] **Step 3: Implement the New Project modal**

```tsx
// apps/web/src/components/projects/NewProjectModal.tsx
import { Button, Modal, TextInput } from "@mantine/core";
import { useState } from "react";

import { useCreateProject } from "../../api/queries";

export function NewProjectModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const create = useCreateProject();

  async function submit() {
    await create.mutateAsync({ name, path });
    setName("");
    setPath("");
    onClose();
  }

  return (
    <Modal opened={opened} onClose={onClose} title="New project">
      <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
      <TextInput label="Path" value={path} onChange={(e) => setPath(e.currentTarget.value)} />
      <Button mt="md" onClick={submit} loading={create.isPending}>
        Create
      </Button>
    </Modal>
  );
}
```

- [ ] **Step 4: Implement the New Session modal**

```tsx
// apps/web/src/components/projects/NewSessionModal.tsx
import { Button, Modal, Select } from "@mantine/core";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAgents, useCreateSession } from "../../api/queries";

export function NewSessionModal({
  opened,
  onClose,
  projectId,
}: {
  opened: boolean;
  onClose: () => void;
  projectId: string;
}) {
  const [agentName, setAgentName] = useState<string | null>(null);
  const { data: agents } = useAgents();
  const create = useCreateSession();
  const navigate = useNavigate();

  async function submit() {
    if (!agentName) return;
    const session = await create.mutateAsync({ project_id: projectId, agent_id: agentName });
    onClose();
    navigate(`/sessions/${session.id}`);
  }

  return (
    <Modal opened={opened} onClose={onClose} title="New session">
      <Select
        label="Agent"
        data={(agents ?? []).map((a) => a.name)}
        value={agentName}
        onChange={setAgentName}
      />
      <Button mt="md" onClick={submit} loading={create.isPending}>
        Create
      </Button>
    </Modal>
  );
}
```

Note: the session's `agent_id` is set to the agent's **name** here; the backend stores it as-is. (Agents are referenced by name in the harness `AgentSpec`, so this is consistent.)

- [ ] **Step 5: Implement the tree**

```tsx
// apps/web/src/components/projects/ProjectTree.tsx
import { Button } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useDeleteProject, useProjects, useSessions } from "../../api/queries";
import { NewProjectModal } from "./NewProjectModal";
import { NewSessionModal } from "./NewSessionModal";

export function ProjectTree() {
  const { data: projects, isLoading, error } = useProjects();
  const { data: sessions } = useSessions();
  const del = useDeleteProject();
  const [projectOpen, projectModal] = useDisclosure(false);
  const [sessionProject, setSessionProject] = useState<string | null>(null);

  if (isLoading) return <p className="menu-label">Loading…</p>;
  if (error) return <p className="menu-label">Failed to load projects</p>;

  return (
    <div>
      <Button size="xs" mb="sm" onClick={projectModal.open}>
        New project
      </Button>
      <ul className="menu-list">
        {(projects ?? []).map((p) => {
          const projectSessions = (sessions ?? [])
            .filter((s) => s.project_id === p.id)
            .sort((a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? ""));
          return (
            <li key={p.id}>
              <div className="is-flex is-justify-content-space-between">
                <span>{p.name}</span>
                <span>
                  <button
                    type="button"
                    aria-label={`New session in ${p.name}`}
                    onClick={() => setSessionProject(p.id)}
                  >
                    +
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete ${p.name}`}
                    onClick={() => del.mutate(p.id)}
                  >
                    ×
                  </button>
                </span>
              </div>
              <ul>
                {projectSessions.map((s, i) => (
                  <li key={s.id}>
                    <Link to={`/sessions/${s.id}`}>Session {i + 1}</Link>
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ul>
      <NewProjectModal opened={projectOpen} onClose={projectModal.close} />
      <NewSessionModal
        opened={sessionProject !== null}
        onClose={() => setSessionProject(null)}
        projectId={sessionProject ?? ""}
      />
    </div>
  );
}
```

- [ ] **Step 6: Render the tree in the shell**

```tsx
// AppShell.tsx — replace the static <ul className="menu-list"> nav block with:
<ProjectTree />
```

(Import `ProjectTree`.)

- [ ] **Step 7: Run to pass + build**

Run: `bun run test` (passes). `bun run build` succeeds.

- [ ] **Step 8: Commit**

```bash
git add apps/web/src
git commit -m "feat(web): add project/session tree with create modals"
```

---

### Task 4: Session page + routing/nav cleanup

**Files:**
- Create: `apps/web/src/pages/SessionPage.tsx`
- Modify: `apps/web/src/App.tsx` (add `/sessions/:id`; remove `/projects`)
- Modify: `apps/web/src/App.test.tsx` (nav assertions)
- Delete: `apps/web/src/pages/ProjectsPage.tsx`
- Test: `apps/web/src/pages/SessionPage.test.tsx`

**Interfaces:**
- Produces: `/sessions/:id` placeholder; "Projects" nav/route removed.

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/pages/SessionPage.test.tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { SessionPage } from "./SessionPage";

test("shows the session id", () => {
  render(
    <MemoryRouter initialEntries={["/sessions/abc123"]}>
      <Routes>
        <Route path="/sessions/:id" element={<SessionPage />} />
      </Routes>
    </MemoryRouter>,
  );
  expect(screen.getByText(/abc123/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Implement the page**

```tsx
// apps/web/src/pages/SessionPage.tsx
import { useParams } from "react-router-dom";

export function SessionPage() {
  const { id } = useParams();
  return (
    <div>
      <h1 className="title">Session</h1>
      <p className="subtitle">{id}</p>
    </div>
  );
}
```

- [ ] **Step 3: Wire routing + remove the projects route**

```tsx
// App.tsx — inside the <Route element={<AppShell />}> children:
<Route index element={<HomePage />} />
<Route path="agents" element={<AgentsPage />} />
<Route path="providers" element={<ProvidersPage />} />
<Route path="sessions/:id" element={<SessionPage />} />
```

(Remove the `projects` route and the `ProjectsPage` import.)

- [ ] **Step 4: Update App.test.tsx**

```tsx
test("renders the shell and home when authenticated", () => {
  useAuthStore.getState().setToken("tok");
  render(<App />);
  // The sidebar now renders the project tree (query is mocked to empty elsewhere or here).
  expect(screen.getByRole("heading", { name: "Home" })).toBeInTheDocument();
});
```

Note: the shell's `ProjectTree` calls the query hooks; in `App.test` they will hit the real `api`. To keep the test hermetic, mock the endpoints in `App.test.tsx` (add `vi.spyOn` for `fetchProjects`/`fetchSessions`/`fetchAgents` resolving to `[]`). Update the earlier "renders the shell navigation" expectation to not depend on the removed "Projects" link (assert on "Home" heading and/or "Agents" nav link from the top nav).

- [ ] **Step 5: Delete the old projects page**

```bash
git rm apps/web/src/pages/ProjectsPage.tsx
```

- [ ] **Step 6: Run tests + build**

Run: `bun run test` (all pass). `bun run build` succeeds.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src
git commit -m "feat(web): add session page; drop projects page in favor of the tree"
```

---

## Self-Review Notes

- **Spec coverage:** backend create/typed changes (1), endpoints + hooks (2), tree + modals (3), session page + routing/nav (4).
- **Extension points used:** FastAPI `response_model`, SQLModel models as responses, TanStack Query (queries/mutations + invalidation), Mantine `<Modal>`/`<Select>`, React Router.
- **Verification note:** the generated schema component names (`Project`, `SessionRow`, `AgentSpec`) and `openapi-fetch` param syntax (`params.path`) are verified against the regenerated `schema.d.ts` during implementation; adjust `endpoints.ts` if names differ.
- **Session agent_id** is the agent's `name` (consistent with the harness referencing agents by name).
