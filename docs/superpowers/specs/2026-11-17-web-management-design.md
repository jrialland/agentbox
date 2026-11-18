# Agents + Providers Management UI — Design Specification

- **Date:** 2026-11-17
- **Status:** Draft (brainstormed, pending implementation plan)
- **Sub-project:** Frontend #4 — provider/agent management UI, plus backend gaps and **end-to-end (Playwright) testing on the real stack**.

## 1. Context and Scope

This sub-project adds the UI to configure LLM providers and create agents, backed by the REST API. The user requires the flows to be validated against the **real stack** (no heavy API mocking), so this sub-project also introduces E2E testing and the backend prerequisites for it (CORS, a seeded dev server, and model persistence).

### 1.1 What this sub-project encompasses

- Backend: CORS, a dev server + admin seed, server-side ids + secret-safe provider reads, model persistence (refresh) + listing, `ModelRepository`, typed responses.
- Frontend: Providers page, Agents page with a full create form, data hooks/endpoints.
- E2E: Playwright config + web servers (backend dev server, Vite, stub models server) + management-flow tests.

### 1.2 Boundaries (out of scope)

- Chat (sub-project 5) and MCP Apps.
- Update (edit) endpoints for agents/providers — create/delete only for now.
- Avatars (RoboHash) in the agent UI — future (the initial spec mandates RoboHash, tracked separately).

### 1.3 Dependencies

- `agentbox-api`, `apps/web` (scaffold/auth/tree), Playwright.

## 2. Decisions and Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **E2E (Playwright) on the real stack** for functionality. | Mocked component tests don't prove the app works; drive the real backend + frontend in a browser. |
| D2 | **Backend CORS** for the SPA origin. | The frontend must call the API cross-origin; without CORS it's blocked. |
| D3 | **Dev server + admin seed** module. | E2E (and local dev) need a login; there's no self-service admin bootstrap. |
| D4 | **Server ids + `ProviderRead` (no api_key)**. | Consistent with earlier hardening; never return secrets. |
| D5 | **Persist models on refresh** + `GET /models`. | `list_models` is fetch-only; agents need a persisted model to reference. |
| D6 | **Stub models HTTP server** in E2E. | Deterministic "refresh models" without external services. |

## 3. Backend Changes

### 3.1 CORS
- `Settings.cors_origins: list[str] = ["http://localhost:5173"]`.
- `create_app` adds `CORSMiddleware` (`allow_origins=settings.cors_origins`, allow methods/headers/credentials).

### 3.2 Dev server + seed
- `agentbox_api/dev_seed.py`: `async seed_admin(session_factory)` — idempotently creates user `admin`/`admin`, a role with all permissions, and links them.
- `agentbox_api/dev_server.py`: creates the engine/factory, `init_db`, `seed_admin`, then runs uvicorn (reads `DATABASE_URL`/`JWT_SECRET`/`PORT` from env). Run via `uv run python -m agentbox_api.dev_server`.

### 3.3 Providers
- `ProviderCreate {name, kind, base_url?, api_key?, models_url?}` → server id; `POST /providers -> ProviderRead`.
- `ProviderRead {id, name, kind, base_url?, models_url?, is_builtin}` (no `api_key`).
- `GET /providers -> list[ProviderRead]`.
- `POST /providers/{pid}/models/refresh -> list[ModelRead]`: call `list_models(provider)`, upsert `models` (dedupe by provider+name, server ids).
- `GET /models -> list[ModelRead]` (`id, provider_id, name`).
- Add `ModelRepository`; typed responses.

### 3.4 Schema
- Regenerate `apps/web/openapi.json` + `schema.d.ts`.

## 4. Frontend

### 4.1 Endpoints & hooks
- `endpoints.ts`: `fetchProviders`, `createProvider`, `deleteProvider`, `refreshModels`, `fetchModels`, plus `createAgent`/`deleteAgent`.
- `queries.ts`: hooks for each (mutations invalidate `providers`/`models`/`agents`).

### 4.2 Providers page (`/providers`)
- List providers (no api_key), a create form/modal (name, kind, base_url, api_key, models_url), delete, and a **Refresh models** action per provider (shows fetched models).

### 4.3 Agents page (`/agents`)
- List agents (name, description, model), delete.
- **Full create form**:
  - Basics: name, description, instructions.
  - Model: `<Select>` from `GET /models`.
  - Tools: native file tool checkboxes (`read_text_file`, `write_file`, `list_directory`) + a dynamic list of MCP server URLs.
  - Modes: editable list (`name` + `write` toggle), prefilled `ask`/`agent`.
  - Sub-agents: multi-select of existing agent names.
- Submits `{name, description, instructions, model, tool_bindings, mode_definitions, sub_agent_ids}`.

## 5. E2E (Playwright)

- Dev deps: `@playwright/test`; install Chromium (`npx playwright install chromium`).
- `apps/web/e2e/stub-server.ts`: Bun HTTP server on `:9999` serving `GET /models` → `{"data": [{"id": "e2e-model"}]}`.
- `apps/web/playwright.config.ts`:
  - `testDir: "./e2e"`, `baseURL: "http://localhost:5173"`.
  - `webServer` (array):
    1. Stub: `bun run e2e/stub-server.ts` (url `http://localhost:9999/models`).
    2. Backend: `uv run python -m agentbox_api.dev_server`, `cwd` repo root, env `{DATABASE_URL: sqlite+aiosqlite:///./e2e.db, JWT_SECRET: <32+ chars>}`, url `http://localhost:8000/openapi.json`.
    3. Frontend: `bun run dev -- --port 5173`, env `{VITE_API_URL: http://localhost:8000}`, url `http://localhost:5173`.
- `apps/web/e2e/management.spec.ts` — one flow:
  1. Log in as `admin`/`admin`.
  2. Providers: create `e2e-provider` (kind `generic`, models_url `http://localhost:9999/models`); **Refresh models**; assert `e2e-model` appears.
  3. Agents: create `e2e-agent` (model `e2e-model`, tick a tool); assert it appears in the list.
  4. Delete `e2e-agent`; assert gone.
- `playwright.config.ts` sets `reporter: [["html", { open: "never" }]]` (cross-platform; no env var needed).
- Script: `"e2e": "playwright test"`.
- `e2e.db` and Playwright output (`test-results/`, `playwright-report/`) are gitignored.

## 6. Testing Strategy

- **Backend pytest** (real DB) — extended for the new endpoints (provider read omits api_key, refresh persists/dedupes, `/models`, CORS smoke).
- **Playwright E2E** — validates the full management flow on the real stack.
- Existing fast unit/component tests remain as wiring checks; **no new mock-heavy tests** for these flows.

## 7. Error Handling

- Mutation errors → Mantine notification.
- Provider refresh failures (unreachable models_url) → notification.

## 8. Open Items / Future Work

- Chat (sub-project 5); MCP Apps.
- Agents/providers edit (PUT) endpoints.
- RoboHash avatars in the agent UI.

## References

- Backend design — `docs/superpowers/specs/2026-11-17-backend-design.md`.
- Projects/tree design — `docs/superpowers/specs/2026-11-17-web-projects-tree-design.md`.
- Playwright — `https://playwright.dev/`.
