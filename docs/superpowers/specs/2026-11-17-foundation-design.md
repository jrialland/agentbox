# Foundation (Monorepo + Data Model + Persistence) — Design Specification

- **Date:** 2026-11-17
- **Status:** Draft (brainstormed, pending implementation plan)
- **Sub-project:** Foundation — Uv Workspaces monorepo scaffold + full data model + SQLite persistence.

## 1. Context and Scope

This specification covers the foundation sub-project of the Agentbox platform: converting the repository into a Uv Workspaces monorepo, defining the full relational data model, and implementing async SQLite persistence.

### 1.1 What this sub-project encompasses

- **Monorepo scaffold** — a Uv Workspace with `packages/*` members.
- **Full data model** — SQLModel tables for users, RBAC, API keys, providers, models, agents, agent cards, projects, sessions, and turns.
- **Async persistence** — async repositories over SQLite (`aiosqlite`) plus Alembic migrations.
- **A harness refactor** — make the harness's session/message-store layer async to honor the "async wherever possible" mandate.

### 1.2 Boundaries (out of scope)

- **Business logic** — RBAC *enforcement*, authentication flows, and API-key *validation* are modeled as data but not implemented here (they belong to the RBAC/auth sub-project).
- **Backend HTTP layer** (FastAPI endpoints) — a later sub-project.
- **LLM provider *implementation*** (making real model calls) — the provider layer sub-project; here we only persist provider/model records.
- **Frontend** — separate sub-project.

### 1.3 Dependencies

- `agentbox-harness` (existing) — provides domain types `AgentSpec`, `Mode`, `ModelBinding`, `Turn`, and the `MessageLogStore` protocol that `agentbox-models` reuses/implements.

## 2. Decisions and Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Full data model + persistence, **no business logic**. | RBAC enforcement/auth stay in a later sub-project; this keeps the foundation focused on schema + storage. |
| D2 | **Shared models package** `agentbox-models`. | The data layer is importable by both the backend and (potentially) other packages without coupling them to the backend. |
| D3 | Agents stored as **relational core + JSON columns**. | Structured columns for queryable fields (name, description, instructions, model_id); JSON columns for the flexible parts (`tool_bindings`, `mode_definitions`, `sub_agent_ids`). |
| D4 | **Alembic** migrations. | Versioned schema evolution is the standard for SQLModel/SQLAlchemy. |
| D5 | **Async everywhere**, including the harness session layer. | The spec mandates async code wherever possible; a sync message store with a backend bridge would contradict this. |
| D6 | **Approach A** — `agentbox-models` depends on `agentbox-harness`. | The harness is already the domain core; reusing its `AgentSpec`/`Turn`/`MessageLogStore` avoids an unnecessary type-relocation refactor. |
| D7 | `SQLiteMessageLogStore` implements the harness's async `MessageLogStore` **directly** (no bridge). | With async everywhere, the harness's `Session` can be backed by SQLite without an adapter layer. |

## 3. Monorepo Scaffold

- Root `pyproject.toml` declares a workspace:
  ```toml
  [tool.uv.workspace]
  members = ["packages/*"]
  ```
- `packages/agentbox-harness` — existing package, joins as a member.
- `packages/agentbox-models` — new package (SQLModel tables + repositories).

## 4. Harness Async Refactor

The harness's session/message-store layer becomes async (currently sync):

- `MessageLogStore` protocol methods → `async def append`, `async def list_turns`, `async def get`.
- `InMemoryMessageLogStore` methods → async.
- `Session.append(turn, parent_id)` → `async`.
- `Session.history()` → `async`.
- `Harness.run(...)` → `async` (awaits `session.history()` and `session.append`).
- `Harness.run_turn(...)` → already async; now `await self.run(...)` and `await session.append(...)`.

`turns_to_messages` remains a pure synchronous function (no I/O). `EventBus`, `RunManager`, and object construction (`build_agent`, `build_subagent_tool`) remain unchanged — they are already async or pure.

## 5. Data Model

SQLModel table definitions (in `agentbox-models`). All tables have a string/UUID primary key `id` and `created_at`/`updated_at` timestamps unless noted.

| Table | Fields (key) |
|---|---|
| `users` | username, email, password_hash, is_active |
| `roles` | name, description |
| `permissions` | name, description |
| `role_permissions` | role_id (FK), permission_id (FK) — association |
| `user_roles` | user_id (FK), role_id (FK) — association |
| `api_keys` | user_id (FK), key_hash, scopes (JSON), expires_at, revoked_at |
| `providers` | name, kind (enum: generic/openai_legacy/openai_responses/anthropic/moonshot/deepseek), base_url, api_key, models_url, is_builtin |
| `models` | provider_id (FK), name |
| `agents` | name, description, instructions, model_id (FK), tool_bindings (JSON), mode_definitions (JSON), sub_agent_ids (JSON), avatar_url, created_by (FK users) |
| `agent_cards` | agent_id (FK), card (JSON) — A2A agent card |
| `projects` | name, path, owner_id (FK users) |
| `sessions` | project_id (FK), agent_id (FK), head_turn_id (branch pointer) |
| `turns` | session_id (FK), role, content, parent_id (self-ref) |

### 5.1 Agent ↔ `AgentSpec` mapping

`AgentRepository.load(name) -> AgentSpec` reconstructs the harness `AgentSpec` from an `agents` row:

- `tool_bindings` JSON → `list[NativeToolBinding | McpToolBinding]`
- `mode_definitions` JSON → `list[Mode]`
- `sub_agent_ids` JSON → `list[str]`
- `model_id` → `ModelBinding(model=<model name>, provider=<provider name>)` (joined via `models`/`providers`).

## 6. Persistence (async)

- Engine: SQLAlchemy `AsyncEngine` over `aiosqlite`.
- Sessions: `AsyncSession` via a session factory.
- Repositories (all async): `AgentRepository`, `ProviderRepository`, `ModelRepository`, `UserRepository`, `RoleRepository`, `PermissionRepository`, `ApiKeyRepository`, `ProjectRepository`, `SessionRepository`, `TurnRepository`.
- `SQLiteMessageLogStore` — implements the harness's async `MessageLogStore` protocol, scoped to a `session_id`; constructed with an `AsyncSession` + `session_id`. This lets the harness persist turns to SQLite directly.

## 7. Migrations

- Alembic configured against the async engine (using a sync engine for migration execution).
- Initial migration creates all tables.

## 8. Testing

- Each repository is tested for CRUD against an async SQLite database (in-memory `aiosqlite` or a temp file).
- `AgentSpec` round-trips through `AgentRepository` (save → load produces an equivalent spec).
- `SQLiteMessageLogStore` satisfies the harness `MessageLogStore` protocol behavior (append/list/get, branch traversal via `Session.history`).
- Harness async refactor is verified by the updated harness test suite (all tests pass after the refactor).

## 9. Open Items / Future Work

- RBAC enforcement and authentication flows (separate sub-project).
- Backend FastAPI layer that injects `SQLiteMessageLogStore` into harness sessions.
- Provider *implementation* (real model calls) — the provider layer sub-project.

## References

- Initial platform spec — `docs/initial_spec.md`.
- Agentic harness design — `docs/superpowers/specs/2026-11-17-agentic-harness-design.md`.
- SQLModel / SQLAlchemy async (`aiosqlite`), Alembic, and Uv Workspaces documentation.
