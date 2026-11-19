# RBAC Administration (Permissions CRUD + Assignments + Admin UI) — Design Specification

- **Date:** 2026-11-17
- **Status:** Draft (brainstormed, pending implementation plan)
- **Sub-project:** RBAC administration — complete the permissions/roles/users management the initial spec requires, with an admin UI.

## 1. Context and Scope

The initial spec requires RBAC: "Roles are linked to permissions. Users are assigned roles. Users holding administrative roles can … Create, delete, and administer other users … Create and administer roles and permissions." (`initial_spec.md:18-26`).

**What already exists:** `Role`/`Permission` + join tables (`tables/auth.py`); enforcement (`require_permission` + `auth_backend.load_user_permissions`); seeding (`dev_seed.seed_admin` grants all `ALL_PERMISSIONS` to `admin`); `POST/GET/DELETE /roles` and `/users`; `GET /auth/me`.

**The gap:** no `/permissions` CRUD; no role↔permission or user↔role assignment endpoints; no role/user update; no admin UI; so a non-admin user created via the API can never be granted permissions, and permission names are frozen at seed time. `GET /users` currently leaks `password_hash`; deleting roles/users leaves orphan join rows.

### 1.1 What this sub-project encompasses
- Permissions CRUD.
- Role↔permission and user↔role assignment (replace-set).
- Role and user update (administering users).
- Safe user read model (no `password_hash`) and link cleanup on delete.
- An admin page (Users / Roles / Permissions tabs) gated by permission.
- Real-stack E2E proving RBAC end to end.

### 1.2 Boundaries
- No DB unique indexes or schema migration (API-level uniqueness checks; the tables are unchanged).
- No new permission names seeded — reuse `roles:manage` and `users:manage`.
- No user self-service/profile page; administration only.
- No API-key scope-subset validation or lifetime (separate backlog item).

## 2. Decisions and Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Reuse `roles:manage` for permissions CRUD + role↔permission + role update; `users:manage` for user update + user↔role. | Avoids seeding a new permission for existing DBs; cohesive RBAC administration. |
| D2 | Assignment is **replace-set** `PUT` (`{permission_ids}` / `{role_ids}`). | Idempotent, one call from a MultiSelect, fewer endpoints than attach/detach. |
| D3 | Uniqueness enforced at the API (409) + permission-name format validation (400). | No migration; simple and sufficient. |
| D4 | `GET/POST /users` return `UserRead {id, username, email, is_active}`. | Fixes the current `password_hash` leak. |
| D5 | Deleting a permission/role/user removes dependent join rows (and a user's API keys). | Prevents orphans and stale grants. |
| D6 | One `AdminPage` at `/admin` with tabs; nav shown only with `roles:manage` or `users:manage`. | User choice; keeps nav tidy; gated. |

## 3. Backend

### 3.1 Permissions (`routers/permissions.py`, guard `roles:manage`)
- `GET /permissions` → `list[PermissionRead {id, name, description}]`.
- `POST /permissions {name, description?}` → create; validate `^[a-z0-9_]+:[a-z0-9_-]+$`; 409 if name exists.
- `PUT /permissions/{pid} {name?, description?}` → update; same validation/uniqueness; 404 unknown.
- `DELETE /permissions/{pid}` → delete the permission and its `RolePermissionLink`s.

### 3.2 Roles (`routers/roles.py`, guard `roles:manage`)
- Existing `GET/POST/DELETE /roles`.
- Add `PUT /roles/{rid} {name?, description?}` → update (uniqueness 409).
- `GET /roles/{rid}/permissions` → `list[PermissionRead]` for the role.
- `PUT /roles/{rid}/permissions {permission_ids: list[str]}` → replace the role's permission set (validate ids exist → 400; delete existing links, insert new).
- `DELETE /roles/{rid}` → also remove `RolePermissionLink`s and `UserRoleLink`s referencing it.

### 3.3 Users (`routers/users.py`, guard `users:manage`)
- `GET /users` → `list[UserRead {id, username, email, is_active}]` (no `password_hash`).
- `POST /users {username, email, password}` → create (returns `UserRead`); 409 if username exists.
- Add `PUT /users/{uid} {email?, is_active?, password?}` → update; hash a provided password; 404 unknown.
- `GET /users/{uid}/roles` → `list[RoleRead {id, name, description}]`.
- `PUT /users/{uid}/roles {role_ids: list[str]}` → replace the user's roles (validate ids → 400).
- `DELETE /users/{uid}` → also remove `UserRoleLink`s and the user's `ApiKey`s.

### 3.4 Shapes and errors
- `PermissionRead {id, name, description}`; `RoleRead {id, name, description}`; `UserRead {id, username, email, is_active}`.
- 404 unknown id; 409 duplicate name/username; 400 invalid permission name or unknown assignment ids.
- Regenerate `apps/web/openapi.json` + `schema.d.ts`.

## 4. Frontend

### 4.1 `AdminPage` (`src/pages/AdminPage.tsx`, route `/admin`)
- Mantine `<Tabs>`: **Users**, **Roles**, **Permissions**.
- **Permissions tab**: table (name, description); a create form (name, description); edit via a Mantine `Modal`; delete.
- **Roles tab**: table (name, description); create/edit/delete; per-role permission `MultiSelect` (submit → `PUT /roles/{rid}/permissions`).
- **Users tab**: table (username, email, active); create (username/email/password); edit (email/active/password optional); delete; per-user role `MultiSelect` (submit → `PUT /users/{uid}/roles`).

### 4.2 Nav gating
- `AppShell`: show an **Admin** link to `/admin` only when `user.permissions` includes `roles:manage` or `users:manage`.

### 4.3 API layer
- `endpoints.ts`: `fetchPermissions/createPermission/updatePermission/deletePermission`, `updateRole`, `fetchRolePermissions/setRolePermissions`, `fetchUsers/createUser/updateUser/deleteUser`, `fetchUserRoles/setUserRoles`.
- `queries.ts`: matching hooks; invalidate the affected query keys on mutation.
- `schema.d.ts` regenerated from the backend.

## 5. Testing

- **Backend pytest** (`tests/test_rbac_admin.py`):
  - permissions CRUD; duplicate → 409; invalid name → 400; delete removes `RolePermissionLink`s.
  - `PUT /roles/{rid}`; `PUT /roles/{rid}/permissions` replaces + validates ids; `GET` returns them; delete role removes `RolePermissionLink` + `UserRoleLink`.
  - `PUT /users/{uid}` (email/active/password); `PUT /users/{uid}/roles` replaces + validates; delete user removes `UserRoleLink` + `ApiKey`.
  - `GET /users` response has no `password_hash`.
  - guards: 403 without the required permission.
- **Frontend Vitest**: `AdminPage` renders the three tabs/tables (queries mocked); an assignment submit calls the right endpoint (mock).
- **E2E** (`e2e/rbac.spec.ts`, real stack): as admin, create permission `projects:read`, a role granted it, a user assigned that role (via the Admin UI); then authenticate as that user and assert `GET /projects` succeeds while creating an agent returns 403.

## 6. Error Handling

- 400 invalid permission name / unknown assignment ids → UI notification.
- 409 duplicate → inline error/notification.
- 404 → notification.
- Deleting the last admin role/user is allowed (no special protection in this scope).

## 7. Open Items / Future Work

- DB unique indexes for `Permission.name` / `Role.name` / `User.username`.
- API-key scope-subset validation + lifetime (separate backlog item).
- Audit logging of RBAC changes.
- Protect against removing the last administrator.

## References

- Initial spec — `docs/initial_spec.md:18-31` (RBAC + API keys).
- Existing RBAC code — `tables/auth.py`, `auth_backend.py`, `deps.py`, `dev_seed.py`, `routers/roles.py`, `routers/users.py`.
