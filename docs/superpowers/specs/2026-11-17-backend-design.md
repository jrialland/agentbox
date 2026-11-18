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
- `pydantic-ai[ag-ui]` — pulls in `ag-ui-protocol` and `starlette` for the AG-UI adapter.
- `pydantic-settings` — `BaseSettings` for configuration (already a transitive dependency).

## 2. Decisions and Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **JWT login + API keys** (two auth paths). | JWT for interactive/web use; API keys for programmatic access (and A2A later). |
| D2 | **bcrypt** for password hashing; **pyjwt** (HS256) for JWTs. | Standard, maintained, minimal. `passlib` is avoided (unmaintained with newer bcrypt). |
| D3 | JWT carries only `sub` (user id); roles/permissions are resolved from the DB per request. | Permission changes take effect immediately; a fresh, correct enforcement. |
| D4 | **Reuse pydantic-ai's `AGUIAdapter` facilities** (`transform_stream` + `streaming_response`/`encode_stream`) over the harness's raw events, instead of a hand-rolled serializer. | pydantic-ai already ships the AG-UI transformation and SSE framing; the harness emits raw `AgentStreamEvent`/`AgentRunResultEvent`s (inside `RunEvent`), so a thin adapter unwraps and pipes them through. |
| D5 | Chat endpoint wires `resolve_model` + `Harness` + `SQLiteMessageLogStore`. | Reuses all three packages; the backend is the integration layer. |
| D6 | RBAC enforced via a `require_permission(...)` dependency. | Centralized, declarative, testable. |
| D7 | **Use Starlette's native auth extension points** — a custom `AuthenticationBackend` returning `(AuthCredentials, BaseUser)`, wired via `AuthenticationMiddleware`, populating `request.user`/`request.auth`. | Reuses the mandated Starlette/FastAPI mechanism instead of a bespoke auth layer; permissions ride in `AuthCredentials.scopes`. |

## 3. Package: `agentbox-api`

- New workspace member `packages/agentbox-api`.
- Layout:
  - `app.py` — FastAPI app + lifespan (engine/session factory).
  - `config.py` — a `pydantic-settings.BaseSettings` subclass (JWT secret as `SecretStr`, DB URL, JWT expiry, etc.) loaded from environment / `.env`.
  - `security.py` — password hashing (bcrypt), JWT sign/verify (pyjwt), API-key hash/lookup.
  - `auth_backend.py` — `JWTAuthenticationBackend(AuthenticationBackend)` returning `(AuthCredentials, User)`; `User(BaseUser)`.
  - `deps.py` — dependencies (DB session, `require_permission` reading `request.auth.scopes`).
  - `routers/` — `auth.py`, `agents.py`, `providers.py`, `projects.py`, `sessions.py`, `users.py`, `api_keys.py`.
  - `streaming.py` — thin adapter: unwraps `RunEvent` → raw pydantic-ai events and pipes them through `AGUIAdapter` (`transform_stream` + `streaming_response`).
  - `schemas.py` — Pydantic request/response DTOs; reuse SQLModel table models directly where the wire format matches, DTOs only for shapes that differ (e.g. `tool_bindings`/`mode_definitions` are JSON strings in the DB but structured on the wire).

## 4. Authentication (Starlette-native)

- A custom `JWTAuthenticationBackend(AuthenticationBackend)` implements `authenticate(request) -> (AuthCredentials, BaseUser) | None`:
  - Reads `Authorization: Bearer <token>`.
  - If the token is a **JWT**: verify signature (pyjwt), load the user + roles + permissions from the DB.
  - If it is an **API key**: hash and look up `api_keys`, resolving the user + the key's `scopes`.
  - Returns `(AuthCredentials(scopes=[permissions...]), User(...))`, or `None` (→ `UnauthenticatedUser`).
- A `User(BaseUser)` subclass carries `id`, `username`, `permissions`, `roles`; implements `is_authenticated`, `display_name`, `identity`.
- `AuthenticationMiddleware` is registered on the FastAPI app, populating `request.user` and `request.auth` in the ASGI scope.

### 4.1 JWT login

- `POST /auth/login` with `{username, password}` (declared via `fastapi.security.HTTPBearer` / `OAuth2PasswordRequestForm` for OpenAPI docs).
- Verifies `password_hash` (bcrypt `checkpw`); on success issues an HS256 JWT with `sub` = user id and an expiry.

### 4.2 API keys

- `POST /api-keys` creates a key: a random secret is generated, its hash stored in `api_keys.key_hash`, with `scopes` (JSON list of permissions, a subset of the user's). The raw secret is returned once.

## 5. RBAC

- Permissions are string names, e.g. `agents:create`, `agents:read`, `agents:update`, `agents:delete`, `providers:create`, `providers:read`, `providers:delete`, `providers:list-models`, `projects:create`, `projects:read`, `projects:delete`, `sessions:create`, `sessions:read`, `users:manage`, `roles:manage`, `api_keys:manage`.
- Roles bind permissions (`role_permissions`); users bind roles (`user_roles`).
- Enforcement: the `require_permission(name)` dependency checks `request.auth.scopes` (the permissions resolved by the backend) and returns 403 if absent. Admin role grants all. Starlette's `requires(...)` decorator is also usable where appropriate.

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
  6. Unwrap each `RunEvent` to its raw pydantic-ai event and pipe it through `AGUIAdapter.transform_stream()` → AG-UI events (`RUN_STARTED`, `TEXT_MESSAGE_*`, `TOOL_CALL_*`, `REASONING_MESSAGE_*`, `CUSTOM`, `RUN_FINISHED`), then `streaming_response()` emits SSE.
- A `RunOutcome` (error/cancelled) maps to `RUN_ERROR`/`RUN_FINISHED(cancelled)`.

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
- `JWTAuthenticationBackend` — unit-test that JWT and API-key requests resolve to `(AuthCredentials, User)` with correct scopes, and that unknown/invalid credentials return `None`.
- `require_permission` — unit-test with stubbed caller contexts.
- Endpoints — FastAPI `TestClient` against an in-memory async SQLite DB (via dependency override).
- Streaming adapter — unit-test that `RunEvent`s unwrap and flow through `transform_stream` into AG-UI events; the real-model path is already covered in `agentbox-providers`.

## 11. Open Items / Future Work

- ACP and A2A adapters (separate sub-projects) — A2A reuses the API-key auth.
- Frontend (React) — consumes this API.
- MCP Apps rendering (frontend).

## References

- Harness design — `docs/superpowers/specs/2026-11-17-agentic-harness-design.md`.
- Foundation design — `docs/superpowers/specs/2026-11-17-foundation-design.md`.
- Provider layer design — `docs/superpowers/specs/2026-11-17-provider-layer-design.md`.
- AG-UI protocol — `https://docs.ag-ui.com/`.
