# Provider / Model Management + Session Delete — Design Specification

- **Date:** 2026-11-17
- **Status:** Draft (brainstormed; approved scope; pending implementation plan)
- **Sub-project:** Provider editing, model management, and session deletion — completing the admin gaps so providers/models can be fully managed from the UI.

## 1. Context and Scope

Today the Providers page can **create** a provider and **refresh** its models, and models are only selectable in the agent form. There is no provider edit, no direct model management, and sessions cannot be deleted from the UI (though ACP `session/delete` removes them server-side).

### 1.1 What this sub-project encompasses
- `PUT /providers/{pid}` + a UI edit modal.
- Model management: `POST /models`, `DELETE /models/{mid}` + a Models tab.
- `DELETE /sessions/{sid}` + a delete action in the project tree.
- Safe deletes: refuse to delete models/providers in use; prevent orphans.
- Shared session-cleanup helper (reused by ACP `session/delete`).

### 1.2 Boundaries
- No provider/model rename uniqueness migration (API-level checks only).
- No model capability/alias editing (name + provider only).
- No bulk operations.

### 1.3 Dependencies
- `agentbox-api`, `agentbox-models`, `apps/web`; no new third-party deps.

## 2. Decisions and Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Reuse `providers:create` for provider update + model mutations; `sessions:create` for session delete. | Existing permissions; no new seed. |
| D2 | `DELETE /models/{mid}` → **409** if an agent uses it. | Prevents breaking agents. |
| D3 | `DELETE /providers/{pid}` → **409** if any of its models is used by an agent; otherwise delete the provider **and its models**. | No orphans; safe. |
| D4 | One shared `delete_session_data(factory, sid)` helper (turns + attachments + row), used by the HTTP router and ACP. | DRY; consistent. |
| D5 | Providers page becomes tabbed (Providers / Models). | User choice; no extra nav. |
| D6 | Session delete lives in the project tree with a confirmation. | Natural location; matches the tree. |

## 3. Backend

### 3.1 Providers (`routers/providers.py`)
- `PUT /providers/{pid}` (`providers:create`), body `ProviderUpdate {name?, kind?, base_url?, api_key?, models_url?}`:
  - Omitted fields are left unchanged (so the API key is never cleared by omission); 404 unknown; returns `ProviderRead`.
- `DELETE /providers/{pid}` (`providers:delete`):
  - 404 unknown.
  - If any model of the provider is referenced by an agent → **409** (`Model in use`).
  - Else delete the provider's models, then the provider.

### 3.2 Models (`routers/models.py`)
- `GET /models` (unchanged).
- `POST /models` (`providers:create`) `{provider_id, name}`:
  - 404 if the provider does not exist.
  - 409 if a model with that name already exists for that provider.
  - Returns the created `Model`.
- `DELETE /models/{mid}` (`providers:create`):
  - 404 unknown; 409 if an agent uses it; else delete.

### 3.3 Sessions (`routers/sessions.py`)
- `DELETE /sessions/{sid}` (`sessions:create`):
  - 404 unknown.
  - Delete the session's turns, attachments, and row via `delete_session_data(factory, sid)`; return `{"ok": true}`.
- `delete_session_data(factory, sid)` (in `runtime.py`): delete `TurnRow`s, `SessionAttachment`s, then the `SessionRow`.
- Refactor ACP `AgentboxAcpAgent.delete_session` to call the same helper.

### 3.4 Guards/errors
- 404 unknown ids.
- 409 model-in-use / duplicate model.

## 4. Frontend

### 4.1 Providers page → tabs (`ProvidersPage.tsx`)
- **Providers tab**: existing create form + table + Refresh/Delete, plus an **Edit** modal (`name`, `kind`, `base_url`, `api_key` (placeholder "leave blank to keep"), `models_url`) → `PUT`.
- **Models tab**: table (`name`, provider) from `useModels`/`useProviders`; create form (`provider` Select + `name` TextInput) → `POST /models`; **Delete** per row → `DELETE /models/{mid}`.

### 4.2 Project tree (`ProjectTree.tsx`)
- Each session row gets a **delete** control; on click, a Mantine confirm modal → `DELETE /sessions/{sid}`; invalidate the sessions query; if the deleted session is the current route, navigate to `/`.

### 4.3 API layer
- `endpoints.ts`: `updateProvider(pid, body)`, `createModel({provider_id, name})`, `deleteModel(mid)`, `deleteSession(sid)`.
- `queries.ts`: matching hooks; invalidate `providers`, `models`, `sessions` as appropriate.
- Regenerate `schema.d.ts`.

## 5. Testing

- **Backend pytest** (`tests/test_provider_model_admin.py`, `tests/test_session_delete.py`):
  - provider PUT updates fields and preserves the API key when omitted.
  - model create / duplicate 409 / delete / delete-in-use 409.
  - provider delete: 409 when a model is in use; otherwise removes the provider and its models.
  - session delete: 404 unknown; removes the row, turns, and attachments.
- **Frontend Vitest**: Providers page shows both tabs; an edit/delete-model/session-delete action calls the right mutation (mocked).
- **E2E** (`e2e/provider-model-admin.spec.ts`): create a provider → refresh models → edit the provider → add a model → delete it → create a session and delete it from the project tree (asserts it disappears).

## 6. Error Handling

- 409 (model in use / duplicate) and 404 → UI notifications.
- Deleting the currently-open session → navigate home.

## 7. Open Items / Future Work

- Unique indexes for provider/model names.
- Model aliases/capabilities.
- Provider connectivity test endpoint.

## References

- Existing code — `routers/providers.py`, `routers/models.py`, `routers/sessions.py`, `repos/crud.py`, `tables/core.py`, `apps/web/src/pages/ProvidersPage.tsx`, `components/projects/ProjectTree.tsx`.
