# Projects + Session Tree — Design Specification

- **Date:** 2026-11-17
- **Status:** Draft (brainstormed, pending implementation plan)
- **Sub-project:** Frontend #3 — project/session management via a left-hand tree, plus backend improvements to the projects/sessions/agents endpoints.

## 1. Context and Scope

The platform groups work into **projects** (folders) each containing **sessions** (agentic conversations). The initial spec mandates a left-hand tree whose roots are projects and whose children are the sessions for each project. This sub-project builds that tree in the `apps/web` SPA (which already has auth + a shell), backed by the existing REST endpoints, with modest backend improvements.

### 1.1 What this sub-project encompasses

- Backend: server-generated ids + owner-from-auth on create endpoints; typed OpenAPI responses for the endpoints the tree consumes.
- Frontend: data hooks (TanStack Query), the project/session tree in the sidebar, "New project"/"New session" modals, a placeholder `/sessions/:id` page, and shell/nav updates.

### 1.2 Boundaries (out of scope)

- The chat UI (sub-project 5) — the session page is a placeholder.
- Agents/providers management UI (sub-project 4) — agents are only read (for the session-create dropdown).
- Session deletion (the backend has no `DELETE /sessions`).
- Per-user project filtering (all projects are listed; ownership-based filtering is future).

### 1.3 Dependencies

- `agentbox-api` (backend), the `apps/web` scaffold + auth (frontend #1/#2).

## 2. Decisions and Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Server-generated ids + owner from auth** on create. | Clients should not mint ids or supply `owner_id`; the server owns identity. Matches the earlier `/auth/me` improvement. |
| D2 | **Type the CRUD responses** (`response_model`/annotations). | The generated client currently gets `unknown`; the tree needs `Project`/`Session`/`Agent` types. |
| D3 | **Tree in the sidebar as primary navigation.** | The initial spec places the project/session tree on the left; it replaces the static "Projects" nav. |
| D4 | **Mantine `<Modal>` + `useDisclosure`** for create flows. | Controlled modals are simple and easy to test. |
| D5 | Session label = **"Session N"** (index per project, by `created_at`). | Sessions have no name field. |
| D6 | Data via **TanStack Query** (hooks + mutations with query invalidation). | Already the chosen server-state tool; keeps the tree in sync after mutations. |

## 3. Backend Changes

### 3.1 Create endpoints
- `POST /projects`: body `{name, path}`; server sets `id = uuid4().hex` and `owner_id = request.user.identity`; returns the created `Project`.
- `POST /sessions`: body `{project_id, agent_id}`; server sets `id = uuid4().hex`; returns the created `SessionRow`.

### 3.2 Typed responses
- `GET /projects` → `list[Project]`; `POST /projects` → `Project`.
- `GET /sessions` → `list[SessionRow]`; `POST /sessions` → `SessionRow`.
- `GET /agents` → `list[AgentSpec]`; `POST /agents` → `AgentSpec` (the harness `AgentSpec` is a Pydantic model).

Use return annotations or `response_model=` so FastAPI populates the OpenAPI response schemas. Regenerate `apps/web/openapi.json` and `schema.d.ts`.

## 4. Frontend: Data Hooks

In `src/api/queries.ts` (or similar):
- `useProjects()` → `api.GET("/projects")`.
- `useSessions()` → `api.GET("/sessions")`.
- `useAgents()` → `api.GET("/agents")`.
- `useCreateProject()` → `api.POST("/projects", { body })`; invalidate projects.
- `useCreateSession()` → `api.POST("/sessions", { body })`; invalidate sessions.
- `useDeleteProject()` → `api.DELETE("/projects/{pid}")`; invalidate projects.

Each exposes `{ data, isLoading, error }` and mutation `{ mutateAsync, isPending }`.

## 5. Frontend: Project Tree

- `ProjectTree` (rendered in the sidebar):
  - "New project" button → opens the New Project modal.
  - For each project: its name, a **+ New session** action (opens the New Session modal with that project), and a delete (trash) action.
  - Under each project: its sessions, labeled "Session 1", "Session 2", … (sorted by `created_at`), each a link to `/sessions/{id}`.
  - Loading / empty / error states.
- Grouping: sessions grouped by `project_id` from `GET /sessions`.

## 6. Frontend: Modals

- **New Project modal**: fields `name`, `path`; on submit → `useCreateProject().mutateAsync` → close.
- **New Session modal**: an agent `<Select>` (from `useAgents`, showing agent `name`); the project is fixed; on submit → `useCreateSession().mutateAsync({ project_id, agent_id })` → close → navigate to `/sessions/{newId}`.

## 7. Frontend: Session Page + Shell

- `/sessions/:id` → `SessionPage` (placeholder showing the session id; chat comes in sub-project 5).
- `AppShell` sidebar renders `<ProjectTree />`; the top nav keeps **Agents**, **Providers**, and the user menu; the "Projects" nav link and `/projects` route/page are removed.

## 8. Error Handling

- Mutation errors surface via a Mantine notification (`@mantine/notifications`).
- Query errors render a small inline message in the tree.

## 9. Testing

- Backend (`httpx`): `POST /projects` uses the authenticated user as owner and a server id; `GET`/`POST` responses are typed; `POST /sessions` generates an id.
- Frontend (Vitest + RTL, mocked `api`):
  - Tree renders projects with grouped sessions.
  - New Project modal creates and refreshes.
  - Clicking a session navigates to `/sessions/:id`.
  - New Session modal creates with the selected agent.

## 10. Open Items / Future Work

- Chat (sub-project 5) replaces the placeholder session page.
- Session delete endpoint/UI, project ownership filtering — future.

## References

- Web scaffold design — `docs/superpowers/specs/2026-11-17-web-scaffold-design.md`.
- Frontend auth design — `docs/superpowers/specs/2026-11-17-web-auth-design.md`.
- Backend design — `docs/superpowers/specs/2026-11-17-backend-design.md`.
