# Backend (FastAPI) — Design Specification

- **Date:** 2026-11-17
- **Status:** Draft (brainstormed, pending implementation plan)
- **Sub-project:** Backend — FastAPI HTTP API wiring the harness, models, and providers into a runnable service with RBAC and JWT authentication.

## 1. Context and Scope

This specification covers the backend, which exposes the platform's use cases (agent management, LLM configuration, projects, and agentic chat) over HTTP, with full RBAC and authentication.

### 1.1 What this sub-project encompasses

- **REST API** — agents, providers (+ model-list fetch), projects, sessions, users, roles, permissions, and personal API keys.
- **Chat streaming** — an AG-UI SSE endpoint that runs the harness and streams events.
- **Authentication** — JWT login (username/password) and personal API keys.
- **RBAC enforcement** — roles and permissions, checked per endpoint.

### 1.2 Boundaries (out of scope)

- The **frontend** (React) — a separate sub-project.
- **ACP / A2A protocol adapters** — separate sub-projects (A2A will reuse the API-key auth here).
- **MCP Apps** rendering — frontend concern.
- Provider/model persistence — already in `agentbox-models`; this sub-project exposes it over HTTP.

### 1.3 Dependencies

- `agentbox-models` — tables and repositories (SQLModel/aiosqlite).
- `agentbox-providers` — `resolve_model` / `list_models`.
- `agentbox-harness` — `Harness`, `Session`, `ToolRegistry`, `FilesystemToolbox`, `EventBus`, `RunEvent`.
- `fastapi`, `uvicorn`, `pyjwt`, `bcrypt`.

## 2. Decisions and Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **JWT login + API keys** (two auth paths). | JWT for interactive/web use; API keys for programmatic access (and A2A later). |
| D2 | **bcrypt** for password hashing; **pyjwt** (HS256) for JWTs. | Standard, maintained, minimal. `passlib` is avoided (unmaintained with newer bcrypt). |
| D3 | JWT carries only `sub` (user id); roles/permissions are resolved from the DB per request. | Permission changes take effect immediately; a fresh, correct enforcement. |
| D4 | **Custom AG-UI serializer** over the harness `EventBus` events. | The harness owns session/persistence/sub-agents; a thin adapter maps its canonical `RunEvent`s to AG-UI SSE without reimplementing the runtime. |
| D5 | Chat endpoint wires `resolve_model` + `Harness` + `SQLiteMessageLogStore`. | Reuses all three packages; the backend is the integration layer. |
| D6 | RBAC enforced via a `require_permission(...)` dependency. | Centralized, declarative, testable. |

## 3. Package: `agentbox-api`

- New workspace member `packages/agentbox-api`.
- Layout:
  - `app.py` — FastAPI app + lifespan (engine/session factory).
  - `config.py` — settings (JWT secret, DB URL) from environment.
  - `security.py` — password hashing, JWT sign/verify, API-key hash/lookup.
  - `deps.py` — dependencies (DB session, current user, `require_permission`).
  - `routers/` — `auth.py`, `agents.py`, `providers.py`, `projects.py`, `sessions.py`, `users.py`, `api_keys.py`.
  - `streaming.py` — AG-UI serializer (`RunEvent` → AG-UI SSE events).
  - `schemas.py` — Pydantic request/response models.

## 4. Authentication

### 4.1 JWT login

- `POST /auth/login` with `{username, password}`.
- Verifies `password_hash` (bcrypt `checkpw`); on success issues an HS256 JWT with `sub` = user id and an expiry.
- Requests authenticate via `Authorization: Bearer <jwt>`.

### 4.2 API keys

- `POST /api-keys` creates a key: a random secret is generated, its hash stored in `api_keys.key_hash`, with `scopes` (JSON list of permissions, a subset of the user's). The raw secret is returned once.
- Programmatic requests send `Authorization: Bearer <api-key>`; the backend hashes and looks it up, resolving the user + scopes.

## 5. RBAC

- Permissions are string names, e.g. `agents:create`, `agents:read`, `agents:update`, `agents:delete`, `providers:create`, `providers:read`, `providers:delete`, `providers:list-models`, `projects:create`, `projects:read`, `projects:delete`, `sessions:create`, `sessions:read`, `users:manage`, `roles:manage`, `api_keys:manage`.
- Roles bind permissions (`role_permissions`); users bind roles (`user_roles`).
- The `require_permission(name)` dependency resolves the caller to a permission set and returns 403 if absent. Admin role grants all.

## 6. Endpoints

| Router | Endpoints |
|---|---|
| `auth` | `POST /auth/login`, `POST /auth/register` |
| `agents` | `GET /agents`, `POST /agents`, `GET /agents/{id}`, `PUT /agents/{id}`, `DELETE /agents/{id}` |
| `providers` | `GET /providers`, `POST /providers`, `GET /providers/{id}`, `DELETE /providers/{id}`, `GET /providers/{id}/models` |
| `projects` | `GET /projects`, `POST /projects`, `GET /projects/{id}`, `DELETE /projects/{id}` |
| `sessions` | `POST /sessions`, `GET /sessions`, `GET /sessions/{id}`, `POST /sessions/{id}/messages` |
| `users` | `GET /users`, `POST /users`, `DELETE /users/{id}` (admin) |
| `roles` / `permissions` | CRUD (admin) |
| `api-keys` | `GET /api-keys`, `POST /api-keys`, `DELETE /api-keys/{id}` |

## 7. Chat Streaming

- `POST /sessions/{id}/messages` with `{content}`:
  1. Load `AgentSpec` (via `AgentRepository`).
  2. Resolve the model (`resolve_model`).
  3. Build a `ToolRegistry` with `FilesystemToolbox` (sandboxed to the project root).
  4. Build `Harness(model, registry, store_factory=SQLiteMessageLogStore)`.
  5. `run_turn`, subscribing to the `EventBus`.
  6. Serialize `RunEvent`s → AG-UI events (`RUN_STARTED`, `TEXT_MESSAGE_START`/`CONTENT`/`END`, `TOOL_CALL_START`/`ARGS`/`END`/`RESULT`, `REASONING_MESSAGE_*`, `CUSTOM`, `RUN_FINISHED`/`RUN_ERROR`) as SSE.
- The serializer is a pure, unit-testable function/generator.

## 8. Data Flow

```
Client → FastAPI → auth dep (JWT/API-key → user+perms)
  → router → repository (SQLite) / resolver (Model) / harness (run)
  → SSE stream (AG-UI) back to client
```

## 9. Error Handling

- Auth failures → 401; permission failures → 403; not-found → 404; validation → 422 (FastAPI).
- Run errors are surfaced as AG-UI `RUN_ERROR` via the serializer (using the harness's `RunOutcome`).

## 10. Testing

- `security.py` — unit-test password hashing and JWT sign/verify round-trips.
- `require_permission` — unit-test with stubbed caller contexts.
- Endpoints — FastAPI `TestClient` against an in-memory async SQLite DB (via dependency override).
- Streaming serializer — unit-test with recorded `RunEvent` sequences; the real-model path is already covered in `agentbox-providers`.

## 11. Open Items / Future Work

- ACP and A2A adapters (separate sub-projects) — A2A reuses the API-key auth.
- Frontend (React) — consumes this API.
- MCP Apps rendering (frontend).

## References

- Harness design — `docs/superpowers/specs/2026-11-17-agentic-harness-design.md`.
- Foundation design — `docs/superpowers/specs/2026-11-17-foundation-design.md`.
- Provider layer design — `docs/superpowers/specs/2026-11-17-provider-layer-design.md`.
- AG-UI protocol — `https://docs.ag-ui.com/`.
