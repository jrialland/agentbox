# Frontend Auth — Design Specification

- **Date:** 2026-11-17
- **Status:** Draft (brainstormed, pending implementation plan)
- **Sub-project:** Frontend #2 — authentication (login, logout, route guard, user menu) plus a small backend `GET /auth/me`.

## 1. Context and Scope

This sub-project adds authentication to the `apps/web` SPA (scaffolded in frontend #1) and a small backend endpoint so the UI knows who is logged in. The backend already provides `POST /auth/login` (JWT) and `POST /auth/register`, and the Starlette `AuthenticationMiddleware` populates `request.user` / `request.auth`.

### 1.1 What this sub-project encompasses

- Backend: `GET /auth/me` returning `{id, username, permissions}`.
- Frontend: auth store (token + user) persisted to **sessionStorage**, a login page, a `RequireAuth` guard, 401 handling, and a user menu with logout.

### 1.2 Boundaries (out of scope)

- Self-service registration UI.
- Permission-gated UI beyond exposing the permission list (used later).
- Password reset, refresh tokens.

### 1.3 Dependencies

- `agentbox-api` (backend) and the `apps/web` scaffold (frontend #1).

## 2. Decisions and Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Add **`GET /auth/me`** (backend). | Login returns only the token; the UI needs the username and permissions. Uses the existing Starlette auth context rather than re-decoding the JWT client-side. |
| D2 | Persist the JWT + user in **sessionStorage** via Zustand `persist`. | Survives refresh within a tab; cleared when the tab closes (chosen over localStorage). |
| D3 | `RequireAuth` guard reads the token reactively. | Clearing the token (logout or 401) re-renders the guard and redirects — one mechanism for both. |
| D4 | 401 responses clear the auth store in the API middleware. | Centralized session-expiry handling; the guard performs the redirect. |

## 3. Backend: `GET /auth/me`

- In `routers/auth.py`:
  - If `not request.user.is_authenticated` → `401`.
  - Return `{"id": request.user.identity, "username": request.user.display_name, "permissions": list(request.auth.scopes) if request.auth else []}`.
- No specific permission required (any authenticated user reads their own info).
- Regenerate `apps/web/openapi.json` and `apps/web/src/api/schema.d.ts`.

## 4. Frontend: Auth Store

- Extend `useAuthStore` (Zustand) to hold `token: string | null` and `user: {id, username, permissions} | null`.
- Actions: `setToken`, `setUser`, `clear` (clears both).
- Persist with Zustand `persist` + `createJSONStorage(() => sessionStorage)`, key `"agentbox-auth"`.

## 5. Frontend: API Client

- Existing JWT middleware already reads `useAuthStore.getState().token`.
- Add an `onResponse` middleware: if `response.status === 401`, call `useAuthStore.getState().clear()`.

## 6. Frontend: Login Page

- Form with username + password; on submit:
  1. `api.POST("/auth/login", { body: { username, password } })`.
  2. On error → show "Invalid credentials".
  3. On success → `setToken(data.access_token)`; `api.GET("/auth/me")` → `setUser(...)`; navigate to the originally requested route (from router state) or `/`.
- Bulma form markup; Mantine for any widget (e.g. notifications).

## 7. Frontend: Route Guard + Routing

- `RequireAuth` component: reads `token`; if absent, `<Navigate to="/login" state={{ from }} replace />`; else `<Outlet />`.
- Routing: `/login` public (no shell); a `RequireAuth`-wrapped `AppShell` containing the app routes (`/`, `/agents`, `/providers`, `/projects`).

## 8. Frontend: User Menu / Logout

- Navbar (in `AppShell`) shows the logged-in `user.username` and a **Logout** action.
- Logout: `clear()` (removes token+user + clears sessionStorage entry) → navigate to `/login`.

## 9. Testing

- Backend (`httpx`): `/auth/me` returns id+username+permissions with a valid JWT; `401` without.
- Frontend (Vitest + RTL):
  - Store persists to `sessionStorage` and rehydrates.
  - Login page: mocked `api.POST`/`api.GET` → token+user set and navigation occurs; error path shows a message.
  - `RequireAuth` redirects to `/login` when no token.
  - Logout clears the store and navigates.

## 10. Open Items / Future Work

- Permission-aware UI (using `user.permissions`) — later sub-projects.
- Registration UI, refresh tokens, password reset — not in scope.

## References

- Web scaffold design — `docs/superpowers/specs/2026-11-17-web-scaffold-design.md`.
- Backend design — `docs/superpowers/specs/2026-11-17-backend-design.md`.
- Starlette authentication — `https://www.starlette.io/authentication/`.
