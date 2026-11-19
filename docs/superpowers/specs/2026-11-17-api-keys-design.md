# API Keys — Lifetime + Scope Validation (and API-keys page) — Design Specification

- **Date:** 2026-11-17
- **Status:** Draft (brainstormed, pending implementation plan)
- **Sub-project:** Personal API keys — optional lifetime, scope-subset validation, soft revocation, a safe read model, and an API-keys page.

## 1. Context and Scope

The initial spec: "Users with the appropriate permission can also create and administer **personal API keys** linked to their account. These API keys: May have a limited lifetime. Are created with a subset of the user's permissions. Allow using the application's API while authenticated." (`initial_spec.md:28-32`).

**What exists:** `ApiKey` table (`id, user_id, key_hash, scopes, expires_at, revoked_at, created_at`); `routers/api_keys.py` create/list/delete (`require_permission("api_keys:manage")`, SHA-256 hash); `auth_backend` falls back to API-key hash lookup and uses the key's `scopes`. **Gaps:** `expires_at` isn't accepted on create, exposed, or enforced; `revoked_at` is unused; scopes aren't validated against the caller's permissions; `GET /api-keys` leaks `key_hash`; keys aren't scoped to their owner; there are no tests or UI.

### 1.1 What this sub-project encompasses
- Optional lifetime (`expires_at`) on create, exposed in reads, enforced at authentication.
- Scope-subset validation on create.
- Soft revocation (`revoked_at`) and enforcement.
- Safe `ApiKeyRead` (no `key_hash`) and personal (own-only) scoping.
- An `/api-keys` page (list/create/reveal-once/revoke), gated by `api_keys:manage`.
- Real-stack E2E proving lifetime/scope/revocation.

### 1.2 Boundaries
- No new table/column (the columns exist).
- No admin-manages-others' keys (keys are personal).
- No key rotation, no HMAC pepper, no rate limiting (future).

### 1.3 Dependencies
- `agentbox-api`, `apps/web`; no new third-party deps.

## 2. Decisions and Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | `expires_at` is an optional absolute UTC datetime; UI offers presets (Never/7/30/90 days). | Precise storage; friendly entry. |
| D2 | On create, every requested scope must be in the caller's effective scopes (`request.auth.scopes`) → 400. | Spec: "subset of the user's permissions". |
| D3 | Delete = **soft revoke** (`revoked_at=now`); rows are kept. | Uses the existing column; preserves an audit trail. |
| D4 | `GET /api-keys` is **personal** (only the caller's keys) and returns `ApiKeyRead` **without `key_hash`**. | Security: keys are personal; never expose hashes. |
| D5 | Authentication rejects keys that are revoked or expired. | A limited-lifetime/revoked key must stop working. |
| D6 | The raw key is shown **once** (create response + a one-time modal). | Standard practice; only the hash is stored. |

## 3. Backend

### 3.1 Create — `POST /api-keys` (`api_keys:manage`)
`ApiKeyCreate { scopes: list[str] = [], expires_at: datetime | None = None }`.
- Dedupe `scopes`.
- Reject any scope not in `request.auth.scopes` → **400** (`Unknown or unauthorized scopes: ...`).
- If `expires_at` given: normalize naive → UTC; must be in the future → **400** otherwise.
- Generate `raw = secrets.token_urlsafe(32)`; store `key_hash = sha256(raw)`, `scopes` JSON, `user_id=request.user.identity`, `expires_at`.
- Return `ApiKeyCreated { key: raw, id, scopes, expires_at, created_at }` (raw shown once).

### 3.2 List — `GET /api-keys` (`api_keys:manage`)
- Return the caller's keys only (`user_id == request.user.identity`) as `list[ApiKeyRead { id, scopes (list), expires_at, revoked_at, created_at }]` (no `key_hash`).

### 3.3 Revoke — `DELETE /api-keys/{kid}` (`api_keys:manage`)
- Only the caller's key (404 if not found/not owned).
- Set `revoked_at = now` if not already set; keep the row. Return `{"ok": true}`.

### 3.4 Authentication (`auth_backend.py`)
- After the API-key hash lookup and user load: reject (return `None`, i.e. unauthenticated → 401) when `revoked_at is not None` or `expires_at` is set and `<= datetime.now(UTC)` (normalize naive `expires_at` to UTC).
- JWT flow unchanged.

### 3.5 Shapes
`ApiKeyRead { id, scopes: list[str], expires_at: datetime | None, revoked_at: datetime | None, created_at: datetime }`; `ApiKeyCreated` = `ApiKeyRead` + `key: str`.

## 4. Frontend

### 4.1 Route + nav
- `/api-keys` → `ApiKeysPage`; nav "API keys" shown only when `user.permissions` includes `api_keys:manage`.

### 4.2 `ApiKeysPage`
- **List** table: short id (first 8 chars), scopes (chips), expiry (or "never"), status (active / expired / revoked), **Revoke** button for active keys.
- **Create** form: `MultiSelect` of scopes populated from `user.permissions`; expiry `Select` preset (Never / 7 / 30 / 90 days) converted to an ISO `expires_at`; "Create key" button.
- On success: a **one-time modal** ("Copy your key now; it won't be shown again") with the raw key in a read-only `TextInput`/code and a Copy button; closing invalidates the list.

### 4.3 API layer
- `endpoints.ts`: `fetchApiKeys`, `createApiKey({scopes, expires_at?})`, `revokeApiKey(id)`; types from `schema.d.ts`.
- `queries.ts`: `useApiKeys`, `useCreateApiKey`, `useRevokeApiKey` (invalidate `api-keys`).

## 5. Testing

- **Backend pytest** (`tests/test_api_keys.py`):
  - create with subset scopes → 200; the raw key authenticates an allowed endpoint; `GET` list has no `key_hash` and only the caller's keys.
  - create with a scope the user lacks → 400.
  - create with a past `expires_at` → 400.
  - valid key works; **expired** key → 401; **revoked** key → 401.
  - `DELETE` sets `revoked_at`, keeps the row; listing shows revoked; a second user cannot see/revoke it.
- **Frontend Vitest**: `ApiKeysPage` renders the list (mocked); create/revoke mutations call the endpoints (mocked).
- **E2E** (`e2e/api-keys.spec.ts`, real stack): admin creates a key (`projects:read`, 7-day) via the UI, reads the displayed raw key, uses it to `GET /projects` (200) and `POST /agents` (403), then revokes it via the UI and confirms the key now returns 401.

## 6. Error Handling

- 400 for unauthorized scopes or a non-future `expires_at` → UI notification.
- 404 for unknown/foreign keys.
- Expired/revoked key at the API → 401 (the SPA clears auth on 401).

## 7. Open Items / Future Work

- Admin management of other users' keys.
- Key rotation / multiple active keys UX, HMAC-pepper hashing, rate limiting.
- Show relative "expires in N days" in the list.

## References

- Initial spec — `docs/initial_spec.md:28-32`.
- Existing code — `routers/api_keys.py`, `auth_backend.py`, `security.py`, `tables/auth.py` (`ApiKey`).
