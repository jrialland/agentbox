# RBAC Administration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` (or `subagent-driven-development`). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Complete RBAC administration — permissions CRUD, role↔permission and user↔role assignment, role/user update, safe user reads, and an admin UI — so non-admin users can actually be granted permissions.

**Architecture:** New `/permissions` router; extend `/roles` and `/users` with update + replace-set assignment endpoints (guarded by `roles:manage` / `users:manage`) and cleanup deletes; a safe `UserRead`. The SPA gets an `/admin` page with Users/Roles/Permissions tabs, gated by the user's permissions.

**Tech Stack:** FastAPI, SQLModel, React 19, Mantine v9, TanStack Query, Playwright.

## Global Constraints

- No DB migration / unique index — API-level uniqueness (409) and validation (400).
- Reuse `roles:manage` (permissions CRUD, role update, role↔permission) and `users:manage` (user update, user↔role).
- Never return `password_hash` from any endpoint.
- Assignments are replace-set (`{permission_ids}` / `{role_ids}`).
- `ruff`/`ty`/`bandit` clean; `bun run test`/`bun run build` pass.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `packages/agentbox-api/src/agentbox_api/routers/permissions.py` | permissions CRUD |
| `.../routers/roles.py` | role update + permission assignment + cleanup |
| `.../routers/users.py` | user read/update + role assignment + cleanup |
| `.../app.py` | include permissions router |
| `packages/agentbox-api/tests/test_permissions_router.py` | permissions tests |
| `packages/agentbox-api/tests/test_roles_rbac.py` | role assignment tests |
| `packages/agentbox-api/tests/test_users_rbac.py` | user read/update/assignment tests |
| `apps/web/src/api/endpoints.ts`, `queries.ts` | API helpers + hooks |
| `apps/web/src/pages/AdminPage.tsx` | tabbed admin UI |
| `apps/web/src/App.tsx`, `components/layout/AppShell.tsx` | route + gated nav |
| `apps/web/src/pages/AdminPage.test.tsx` | Vitest |
| `apps/web/e2e/rbac.spec.ts` | E2E |

---

### Task 1: Backend — permissions router

**Files:**
- Create: `packages/agentbox-api/src/agentbox_api/routers/permissions.py`
- Modify: `packages/agentbox-api/src/agentbox_api/app.py`
- Create: `packages/agentbox-api/tests/test_permissions_router.py`

**Interfaces:**
- Produces: `GET/POST /permissions`, `PUT/DELETE /permissions/{pid}`; `PermissionRead {id, name, description}`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_permissions_router.py`:
```python
import httpx
import pytest

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import (
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)


async def _setup(perms=("roles:manage",)):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw")))
        s.add(Role(id="r1", name="admin"))
        for i, p in enumerate(perms):
            s.add(Permission(id=f"p{i}", name=p))
            s.add(RolePermissionLink(role_id="r1", permission_id=f"p{i}"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        await s.commit()
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return engine, client, factory


async def _auth(client) -> dict:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_permissions_crud():
    engine, client, _ = await _setup()
    try:
        h = await _auth(client)
        r = await client.post(
            "/permissions", json={"name": "agents:read", "description": "d"}, headers=h
        )
        assert r.status_code == 200
        pid = r.json()["id"]
        r = await client.get("/permissions", headers=h)
        assert any(p["name"] == "agents:read" for p in r.json())
        r = await client.put(
            f"/permissions/{pid}", json={"description": "updated"}, headers=h
        )
        assert r.json()["description"] == "updated"
        r = await client.delete(f"/permissions/{pid}", headers=h)
        assert r.status_code == 200
        r = await client.get("/permissions", headers=h)
        assert all(p["id"] != pid for p in r.json())
    finally:
        await client.aclose()
        await engine.dispose()


async def test_permission_duplicate_409():
    engine, client, _ = await _setup()
    try:
        h = await _auth(client)
        await client.post("/permissions", json={"name": "x:y"}, headers=h)
        r = await client.post("/permissions", json={"name": "x:y"}, headers=h)
        assert r.status_code == 409
    finally:
        await client.aclose()
        await engine.dispose()


async def test_permission_invalid_name_400():
    engine, client, _ = await _setup()
    try:
        h = await _auth(client)
        r = await client.post("/permissions", json={"name": "bad name"}, headers=h)
        assert r.status_code == 400
    finally:
        await client.aclose()
        await engine.dispose()


async def test_permission_delete_removes_role_links():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        r = await client.post("/permissions", json={"name": "z:z"}, headers=h)
        pid = r.json()["id"]
        async with factory() as s:
            s.add(RolePermissionLink(role_id="r1", permission_id=pid))
            await s.commit()
        await client.delete(f"/permissions/{pid}", headers=h)
        async with factory() as s:
            from sqlmodel import select
            links = (
                await s.execute(
                    select(RolePermissionLink).where(
                        RolePermissionLink.permission_id == pid
                    )
                )
            ).scalars().all()
        assert links == []
    finally:
        await client.aclose()
        await engine.dispose()


async def test_permissions_requires_permission():
    engine, client, _ = await _setup(perms=())
    try:
        h = await _auth(client)
        r = await client.get("/permissions", headers=h)
        assert r.status_code == 403
    finally:
        await client.aclose()
        await engine.dispose()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/agentbox-api/tests/test_permissions_router.py -q`
Expected: FAIL (404 route not found).

- [ ] **Step 3: Implement `routers/permissions.py`**

```python
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_models.tables.auth import Permission, RolePermissionLink

router = APIRouter(prefix="/permissions", tags=["permissions"])

_NAME_RE = re.compile(r"[a-z0-9_]+:[a-z0-9_-]+")


class PermissionRead(BaseModel):
    id: str
    name: str
    description: str | None = None


class PermissionCreate(BaseModel):
    name: str
    description: str | None = None


class PermissionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


def _validate_name(name: str) -> None:
    if not _NAME_RE.fullmatch(name):
        raise HTTPException(status_code=400, detail="Invalid permission name")


async def _get_or_404(session, pid: str) -> Permission:
    perm = (
        await session.execute(select(Permission).where(Permission.id == pid))
    ).scalars().first()
    if perm is None:
        raise HTTPException(status_code=404, detail="Not found")
    return perm


@router.get("", response_model=list[PermissionRead])
async def list_permissions(
    request: Request, _=Depends(require_permission("roles:manage"))
):
    async with request.app.state.session_factory() as s:
        rows = (await s.execute(select(Permission))).scalars().all()
    return rows


@router.post("", response_model=PermissionRead)
async def create_permission(
    body: PermissionCreate, request: Request, _=Depends(require_permission("roles:manage"))
):
    _validate_name(body.name)
    async with request.app.state.session_factory() as s:
        existing = (
            await s.execute(select(Permission).where(Permission.name == body.name))
        ).scalars().first()
        if existing is not None:
            raise HTTPException(status_code=409, detail="Permission already exists")
        perm = Permission(
            id=uuid.uuid4().hex, name=body.name, description=body.description
        )
        s.add(perm)
        await s.commit()
        await s.refresh(perm)
    return perm


@router.put("/{pid}", response_model=PermissionRead)
async def update_permission(
    pid: str, body: PermissionUpdate, request: Request, _=Depends(require_permission("roles:manage"))
):
    async with request.app.state.session_factory() as s:
        perm = await _get_or_404(s, pid)
        if body.name is not None:
            _validate_name(body.name)
            dup = (
                await s.execute(
                    select(Permission).where(
                        Permission.name == body.name, Permission.id != pid
                    )
                )
            ).scalars().first()
            if dup is not None:
                raise HTTPException(status_code=409, detail="Permission already exists")
            perm.name = body.name
        if body.description is not None:
            perm.description = body.description
        s.add(perm)
        await s.commit()
        await s.refresh(perm)
    return perm


@router.delete("/{pid}")
async def delete_permission(
    pid: str, request: Request, _=Depends(require_permission("roles:manage"))
):
    async with request.app.state.session_factory() as s:
        perm = await _get_or_404(s, pid)
        await s.execute(
            delete(RolePermissionLink).where(RolePermissionLink.permission_id == pid)
        )
        await s.delete(perm)
        await s.commit()
    return {"ok": True}
```

- [ ] **Step 4: Include the router in `app.py`**

Add `from agentbox_api.routers.permissions import router as permissions_router` and `app.include_router(permissions_router)`.

- [ ] **Step 5: Run tests + lint + commit**

Run: `uv run pytest packages/agentbox-api/tests/test_permissions_router.py -q` → 5 passed.
Run: `uv run ruff check packages/agentbox-api` → clean.
```bash
git add packages/agentbox-api/src/agentbox_api/routers/permissions.py packages/agentbox-api/src/agentbox_api/app.py packages/agentbox-api/tests/test_permissions_router.py
git commit -m "feat(api): permissions CRUD router"
```

---

### Task 2: Backend — role update + permission assignment

**Files:**
- Modify: `routers/roles.py`
- Create: `tests/test_roles_rbac.py`

**Interfaces:**
- Produces: `PUT /roles/{rid}`; `GET/PUT /roles/{rid}/permissions` (`{permission_ids}`).

- [ ] **Step 1: Write failing tests**

Create `tests/test_roles_rbac.py`:
```python
import httpx
from sqlmodel import select

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import (
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)


async def _setup():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw")))
        s.add(Role(id="r1", name="admin"))
        s.add(Permission(id="perm1", name="roles:manage"))
        s.add(RolePermissionLink(role_id="r1", permission_id="perm1"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(Role(id="r2", name="viewer"))
        s.add(Permission(id="perm2", name="projects:read"))
        await s.commit()
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return engine, client, factory


async def _auth(client) -> dict:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_role_update_and_assignment():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        r = await client.put("/roles/r2", json={"name": "reader"}, headers=h)
        assert r.json()["name"] == "reader"
        r = await client.put(
            "/roles/r2/permissions", json={"permission_ids": ["perm2"]}, headers=h
        )
        assert r.status_code == 200
        r = await client.get("/roles/r2/permissions", headers=h)
        assert [p["name"] for p in r.json()] == ["projects:read"]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_role_assignment_unknown_id_400():
    engine, client, _ = await _setup()
    try:
        h = await _auth(client)
        r = await client.put(
            "/roles/r2/permissions", json={"permission_ids": ["nope"]}, headers=h
        )
        assert r.status_code == 400
    finally:
        await client.aclose()
        await engine.dispose()


async def test_delete_role_cleans_links():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        await client.delete("/roles/r2", headers=h)
        async with factory() as s:
            links = (
                await s.execute(
                    select(RolePermissionLink).where(RolePermissionLink.role_id == "r2")
                )
            ).scalars().all()
        assert links == []
    finally:
        await client.aclose()
        await engine.dispose()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/agentbox-api/tests/test_roles_rbac.py -q`
Expected: FAIL (PUT route missing).

- [ ] **Step 3: Implement in `routers/roles.py`**

Add imports: `select`, `delete` (from `sqlalchemy`), `Permission`, `RolePermissionLink`, `UserRoleLink`. Add:
```python
class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class PermissionIds(BaseModel):
    permission_ids: list[str] = []


class PermissionRead(BaseModel):
    id: str
    name: str
    description: str | None = None


@router.put("/{rid}")
async def update_role(
    rid: str, body: RoleUpdate, request: Request, _=Depends(require_permission("roles:manage"))
):
    async with request.app.state.session_factory() as s:
        role = (
            await s.execute(select(Role).where(Role.id == rid))
        ).scalars().first()
        if role is None:
            raise HTTPException(status_code=404, detail="Not found")
        if body.name is not None:
            dup = (
                await s.execute(
                    select(Role).where(Role.name == body.name, Role.id != rid)
                )
            ).scalars().first()
            if dup is not None:
                raise HTTPException(status_code=409, detail="Role already exists")
            role.name = body.name
        if body.description is not None:
            role.description = body.description
        s.add(role)
        await s.commit()
        await s.refresh(role)
    return role


@router.get("/{rid}/permissions", response_model=list[PermissionRead])
async def get_role_permissions(
    rid: str, request: Request, _=Depends(require_permission("roles:manage"))
):
    async with request.app.state.session_factory() as s:
        rows = (
            await s.execute(
                select(Permission)
                .join(RolePermissionLink, RolePermissionLink.permission_id == Permission.id)
                .where(RolePermissionLink.role_id == rid)
            )
        ).scalars().all()
    return rows


@router.put("/{rid}/permissions", response_model=list[PermissionRead])
async def set_role_permissions(
    rid: str, body: PermissionIds, request: Request, _=Depends(require_permission("roles:manage"))
):
    async with request.app.state.session_factory() as s:
        role = (
            await s.execute(select(Role).where(Role.id == rid))
        ).scalars().first()
        if role is None:
            raise HTTPException(status_code=404, detail="Not found")
        if body.permission_ids:
            found = (
                await s.execute(
                    select(Permission.id).where(Permission.id.in_(body.permission_ids))  # ty: ignore[missing-attribute]
                )
            ).scalars().all()
            if set(found) != set(body.permission_ids):
                raise HTTPException(status_code=400, detail="Unknown permission id")
        await s.execute(
            delete(RolePermissionLink).where(RolePermissionLink.role_id == rid)
        )
        for pid in body.permission_ids:
            s.add(RolePermissionLink(role_id=rid, permission_id=pid))
        await s.commit()
        rows = (
            await s.execute(
                select(Permission)
                .join(RolePermissionLink, RolePermissionLink.permission_id == Permission.id)
                .where(RolePermissionLink.role_id == rid)
            )
        ).scalars().all()
    return rows
```
Update `delete_role`:
```python
@router.delete("/{rid}")
async def delete_role(rid: str, request: Request, _=Depends(require_permission("roles:manage"))):
    async with request.app.state.session_factory() as s:
        role = (
            await s.execute(select(Role).where(Role.id == rid))
        ).scalars().first()
        if role is not None:
            await s.execute(delete(RolePermissionLink).where(RolePermissionLink.role_id == rid))
            await s.execute(delete(UserRoleLink).where(UserRoleLink.role_id == rid))
            await s.delete(role)
            await s.commit()
    return {"ok": True}
```
Also add `HTTPException` to the fastapi import (currently `from fastapi import APIRouter, Depends, Request`).

- [ ] **Step 4: Run tests + lint + commit**

Run: `uv run pytest packages/agentbox-api/tests/test_roles_rbac.py -q` → 3 passed.
Run: `uv run ruff check packages/agentbox-api` → clean.
```bash
git add packages/agentbox-api/src/agentbox_api/routers/roles.py packages/agentbox-api/tests/test_roles_rbac.py
git commit -m "feat(api): role update + permission assignment"
```

---

### Task 3: Backend — users read/update + role assignment + schema regen

**Files:**
- Modify: `routers/users.py`
- Create: `tests/test_users_rbac.py`
- Regenerate: `apps/web/openapi.json`, `apps/web/src/api/schema.d.ts`

**Interfaces:**
- Produces: `GET/POST /users` → `UserRead {id, username, email, is_active}`; `PUT /users/{uid}`; `GET/PUT /users/{uid}/roles` (`{role_ids}`).

- [ ] **Step 1: Write failing tests**

Create `tests/test_users_rbac.py`:
```python
import httpx
from sqlmodel import select

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password, verify_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import (
    ApiKey,
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)


async def _setup():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw")))
        s.add(Role(id="r1", name="admin"))
        s.add(Permission(id="perm1", name="users:manage"))
        s.add(RolePermissionLink(role_id="r1", permission_id="perm1"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(Role(id="r2", name="viewer"))
        await s.commit()
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return engine, client, factory


async def _auth(client) -> dict:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_users_list_has_no_password_hash():
    engine, client, _ = await _setup()
    try:
        h = await _auth(client)
        r = await client.get("/users", headers=h)
        assert all("password_hash" not in u for u in r.json())
        assert {"id", "username", "email", "is_active"} <= set(r.json()[0])
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_update_and_assign_roles():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        r = await client.post(
            "/users",
            json={"username": "bob", "email": "b@x", "password": "pw"},
            headers=h,
        )
        uid = r.json()["id"]
        assert "password_hash" not in r.json()
        r = await client.put(
            f"/users/{uid}", json={"is_active": False}, headers=h
        )
        assert r.json()["is_active"] is False
        r = await client.put(
            f"/users/{uid}/roles", json={"role_ids": ["r2"]}, headers=h
        )
        assert r.status_code == 200
        r = await client.get(f"/users/{uid}/roles", headers=h)
        assert [x["name"] for x in r.json()] == ["viewer"]
        # password reset
        await client.put(f"/users/{uid}", json={"password": "newpw"}, headers=h)
        async with factory() as s:
            u = await s.get(User, uid)
        assert verify_password("newpw", u.password_hash)
    finally:
        await client.aclose()
        await engine.dispose()


async def test_delete_user_cleans_links_and_keys():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        r = await client.post(
            "/users", json={"username": "bob", "email": "b@x", "password": "pw"}, headers=h
        )
        uid = r.json()["id"]
        await client.put(f"/users/{uid}/roles", json={"role_ids": ["r2"]}, headers=h)
        async with factory() as s:
            s.add(ApiKey(id="k1", user_id=uid, key_hash="h"))
            await s.commit()
        await client.delete(f"/users/{uid}", headers=h)
        async with factory() as s:
            links = (
                await s.execute(select(UserRoleLink).where(UserRoleLink.user_id == uid))
            ).scalars().all()
            keys = (
                await s.execute(select(ApiKey).where(ApiKey.user_id == uid))
            ).scalars().all()
        assert links == [] and keys == []
    finally:
        await client.aclose()
        await engine.dispose()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/agentbox-api/tests/test_users_rbac.py -q`
Expected: FAIL (PUT routes missing / password_hash leak).

- [ ] **Step 3: Implement in `routers/users.py`**

Replace the file with:
```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_api.security import hash_password
from agentbox_models.repos.crud import UserRepository
from agentbox_models.tables.auth import (
    ApiKey,
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    username: str
    email: str
    password: str


class UserUpdate(BaseModel):
    email: str | None = None
    is_active: bool | None = None
    password: str | None = None


class RoleIds(BaseModel):
    role_ids: list[str] = []


class UserRead(BaseModel):
    id: str
    username: str
    email: str
    is_active: bool


class RoleRead(BaseModel):
    id: str
    name: str
    description: str | None = None


@router.post("", response_model=UserRead)
async def create_user(
    body: UserCreate, request: Request, _=Depends(require_permission("users:manage"))
):
    async with request.app.state.session_factory() as s:
        existing = (
            await s.execute(select(User).where(User.username == body.username))
        ).scalars().first()
        if existing is not None:
            raise HTTPException(status_code=409, detail="Username already exists")
        user = User(
            id=uuid.uuid4().hex,
            username=body.username,
            email=body.email,
            password_hash=hash_password(body.password),
        )
        s.add(user)
        await s.commit()
        await s.refresh(user)
    return user


@router.get("", response_model=list[UserRead])
async def list_users(request: Request, _=Depends(require_permission("users:manage"))):
    return await UserRepository(request.app.state.session_factory).list()


@router.put("/{uid}", response_model=UserRead)
async def update_user(
    uid: str, body: UserUpdate, request: Request, _=Depends(require_permission("users:manage"))
):
    async with request.app.state.session_factory() as s:
        user = (await s.execute(select(User).where(User.id == uid))).scalars().first()
        if user is None:
            raise HTTPException(status_code=404, detail="Not found")
        if body.email is not None:
            user.email = body.email
        if body.is_active is not None:
            user.is_active = body.is_active
        if body.password is not None:
            user.password_hash = hash_password(body.password)
        s.add(user)
        await s.commit()
        await s.refresh(user)
    return user


@router.get("/{uid}/roles", response_model=list[RoleRead])
async def get_user_roles(
    uid: str, request: Request, _=Depends(require_permission("users:manage"))
):
    async with request.app.state.session_factory() as s:
        rows = (
            await s.execute(
                select(Role)
                .join(UserRoleLink, UserRoleLink.role_id == Role.id)
                .where(UserRoleLink.user_id == uid)
            )
        ).scalars().all()
    return rows


@router.put("/{uid}/roles", response_model=list[RoleRead])
async def set_user_roles(
    uid: str, body: RoleIds, request: Request, _=Depends(require_permission("users:manage"))
):
    async with request.app.state.session_factory() as s:
        user = (await s.execute(select(User).where(User.id == uid))).scalars().first()
        if user is None:
            raise HTTPException(status_code=404, detail="Not found")
        if body.role_ids:
            found = (
                await s.execute(select(Role.id).where(Role.id.in_(body.role_ids)))  # ty: ignore[missing-attribute]
            ).scalars().all()
            if set(found) != set(body.role_ids):
                raise HTTPException(status_code=400, detail="Unknown role id")
        await s.execute(delete(UserRoleLink).where(UserRoleLink.user_id == uid))
        for rid in body.role_ids:
            s.add(UserRoleLink(user_id=uid, role_id=rid))
        await s.commit()
        rows = (
            await s.execute(
                select(Role)
                .join(UserRoleLink, UserRoleLink.role_id == Role.id)
                .where(UserRoleLink.user_id == uid)
            )
        ).scalars().all()
    return rows


@router.delete("/{uid}")
async def delete_user(
    uid: str, request: Request, _=Depends(require_permission("users:manage"))
):
    async with request.app.state.session_factory() as s:
        user = (await s.execute(select(User).where(User.id == uid))).scalars().first()
        if user is not None:
            await s.execute(delete(UserRoleLink).where(UserRoleLink.user_id == uid))
            await s.execute(delete(ApiKey).where(ApiKey.user_id == uid))
            await s.delete(user)
            await s.commit()
    return {"ok": True}
```

- [ ] **Step 4: Run tests, full suite, lint**

Run: `uv run pytest packages/agentbox-api/tests/test_users_rbac.py -q` → 3 passed.
Run: `uv run pytest packages/agentbox-api/tests -q` → all pass (fix any existing test asserting the old `/users` shape).
Run: `uv run ruff check packages/agentbox-api` → clean.

- [ ] **Step 5: Regenerate the client schema and commit**

```bash
uv run python -c "import json; from agentbox_api.app import create_app; from agentbox_api.config import Settings; open('apps/web/openapi.json','w',encoding='utf-8').write(json.dumps(create_app(Settings(jwt_secret='x'*32)).openapi(), indent=2))"
```
```powershell
Set-Location apps/web; bun run codegen
```
```bash
git add packages/agentbox-api/src/agentbox_api/routers/users.py packages/agentbox-api/tests/test_users_rbac.py apps/web/openapi.json apps/web/src/api/schema.d.ts
git commit -m "feat(api): user read/update + role assignment; safe UserRead"
```

---

### Task 4: Frontend — API helpers + hooks

**Files:**
- Modify: `apps/web/src/api/endpoints.ts`, `apps/web/src/api/queries.ts`

**Interfaces:**
- Produces: `fetchPermissions/createPermission/updatePermission/deletePermission`, `updateRole`, `fetchRolePermissions/setRolePermissions`, `fetchRoles`, `fetchUsers/createUser/updateUser/deleteUser`, `fetchUserRoles/setUserRoles`; hooks incl. `usePermissions`, `useRoles`, `useUsers`, and mutations.

- [ ] **Step 1: Implement endpoints**

In `endpoints.ts`, add types `Permission = components["schemas"]["PermissionRead"]`, `Role = components["schemas"]["RoleRead"]`, `User = components["schemas"]["UserRead"]`, and:
```ts
export async function fetchPermissions(): Promise<Permission[]> {
  const { data } = await api.GET("/permissions");
  return data ?? [];
}
export async function createPermission(body: { name: string; description?: string }): Promise<Permission> {
  const { data, error } = await api.POST("/permissions", { body });
  if (error) throw new Error("Failed to create permission");
  return data as Permission;
}
export async function updatePermission(pid: string, body: { name?: string; description?: string }): Promise<Permission> {
  const { data, error } = await api.PUT("/permissions/{pid}", { params: { path: { pid } }, body });
  if (error) throw new Error("Failed to update permission");
  return data as Permission;
}
export async function deletePermission(pid: string): Promise<void> {
  await api.DELETE("/permissions/{pid}", { params: { path: { pid } } });
}
export async function fetchRoles(): Promise<Role[]> {
  const { data } = await api.GET("/roles");
  return data ?? [];
}
export async function createRole(body: { name: string; description?: string }): Promise<Role> {
  const { data, error } = await api.POST("/roles", { body });
  if (error) throw new Error("Failed to create role");
  return data as Role;
}
export async function deleteRole(rid: string): Promise<void> {
  await api.DELETE("/roles/{rid}", { params: { path: { rid } } });
}
export async function updateRole(rid: string, body: { name?: string; description?: string }): Promise<Role> {
  const { data, error } = await api.PUT("/roles/{rid}", { params: { path: { rid } }, body });
  if (error) throw new Error("Failed to update role");
  return data as Role;
}
export async function fetchRolePermissions(rid: string): Promise<Permission[]> {
  const { data } = await api.GET("/roles/{rid}/permissions", { params: { path: { rid } } });
  return data ?? [];
}
export async function setRolePermissions(rid: string, permissionIds: string[]): Promise<Permission[]> {
  const { data, error } = await api.PUT("/roles/{rid}/permissions", {
    params: { path: { rid } },
    body: { permission_ids: permissionIds },
  });
  if (error) throw new Error("Failed to set role permissions");
  return data ?? [];
}
export async function fetchUsers(): Promise<User[]> {
  const { data } = await api.GET("/users");
  return data ?? [];
}
export async function createUser(body: { username: string; email: string; password: string }): Promise<User> {
  const { data, error } = await api.POST("/users", { body });
  if (error) throw new Error("Failed to create user");
  return data as User;
}
export async function updateUser(uid: string, body: { email?: string; is_active?: boolean; password?: string }): Promise<User> {
  const { data, error } = await api.PUT("/users/{uid}", { params: { path: { uid } }, body });
  if (error) throw new Error("Failed to update user");
  return data as User;
}
export async function deleteUser(uid: string): Promise<void> {
  await api.DELETE("/users/{uid}", { params: { path: { uid } } });
}
export async function fetchUserRoles(uid: string): Promise<Role[]> {
  const { data } = await api.GET("/users/{uid}/roles", { params: { path: { uid } } });
  return data ?? [];
}
export async function setUserRoles(uid: string, roleIds: string[]): Promise<Role[]> {
  const { data, error } = await api.PUT("/users/{uid}/roles", {
    params: { path: { uid } },
    body: { role_ids: roleIds },
  });
  if (error) throw new Error("Failed to set user roles");
  return data ?? [];
}
```

- [ ] **Step 2: Implement hooks in `queries.ts`**

Add the imports and:
```ts
export function usePermissions() {
  return useQuery({ queryKey: ["permissions"], queryFn: fetchPermissions });
}
export function useRoles() {
  return useQuery({ queryKey: ["roles"], queryFn: fetchRoles });
}
export function useUsers() {
  return useQuery({ queryKey: ["users"], queryFn: fetchUsers });
}
export function useRolePermissions(rid: string | null) {
  return useQuery({
    queryKey: ["role-permissions", rid],
    queryFn: () => fetchRolePermissions(rid as string),
    enabled: !!rid,
  });
}
export function useUserRoles(uid: string | null) {
  return useQuery({
    queryKey: ["user-roles", uid],
    queryFn: () => fetchUserRoles(uid as string),
    enabled: !!uid,
  });
}
export function useCreatePermission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createPermission,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["permissions"] }),
  });
}
export function useUpdatePermission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ pid, body }: { pid: string; body: { name?: string; description?: string } }) =>
      updatePermission(pid, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["permissions"] }),
  });
}
export function useDeletePermission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deletePermission,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["permissions"] }),
  });
}
export function useCreateRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createRole,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["roles"] }),
  });
}
export function useUpdateRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ rid, body }: { rid: string; body: { name?: string; description?: string } }) =>
      updateRole(rid, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["roles"] }),
  });
}
export function useDeleteRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteRole,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["roles"] }),
  });
}
export function useSetRolePermissions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ rid, ids }: { rid: string; ids: string[] }) =>
      setRolePermissions(rid, ids),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ["role-permissions", v.rid] });
      qc.invalidateQueries({ queryKey: ["roles"] });
    },
  });
}
export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createUser,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}
export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uid, body }: { uid: string; body: { email?: string; is_active?: boolean; password?: string } }) =>
      updateUser(uid, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}
export function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteUser,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}
export function useSetUserRoles() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uid, ids }: { uid: string; ids: string[] }) => setUserRoles(uid, ids),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ["user-roles", v.uid] });
      qc.invalidateQueries({ queryKey: ["users"] });
    },
  });
}
```

- [ ] **Step 3: Build + commit**

```powershell
Set-Location apps/web; bun run build
```
```bash
git add apps/web/src/api/endpoints.ts apps/web/src/api/queries.ts
git commit -m "feat(web): RBAC API helpers + query hooks"
```

---

### Task 5: Frontend — Admin page shell + Permissions tab + route/nav

**Files:**
- Create: `apps/web/src/pages/AdminPage.tsx`
- Modify: `apps/web/src/App.tsx`, `apps/web/src/components/layout/AppShell.tsx`
- Create: `apps/web/src/pages/AdminPage.test.tsx`

- [ ] **Step 1: Write failing test**

Create `AdminPage.test.tsx`:
```tsx
import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("../api/queries", () => ({
  usePermissions: () => ({ data: [{ id: "p1", name: "agents:read", description: "d" }] }),
  useCreatePermission: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdatePermission: () => ({ mutateAsync: vi.fn() }),
  useDeletePermission: () => ({ mutateAsync: vi.fn() }),
  useRoles: () => ({ data: [] }),
  useUsers: () => ({ data: [] }),
}));

import { AdminPage } from "./AdminPage";

test("renders tabs and permissions", () => {
  render(
    <MantineProvider>
      <AdminPage />
    </MantineProvider>,
  );
  expect(screen.getByRole("tab", { name: "Permissions" })).toBeInTheDocument();
  expect(screen.getByText("agents:read")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

```powershell
Set-Location apps/web; bun run test AdminPage
```

- [ ] **Step 3: Implement `AdminPage` (shell + Permissions tab)**

```tsx
import { Button, Modal, Tabs, Table, TextInput, Textarea } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import type { Permission } from "../api/endpoints";
import {
  useCreatePermission,
  useDeletePermission,
  usePermissions,
  useUpdatePermission,
} from "../api/queries";

export function AdminPage() {
  return (
    <div>
      <h1 className="title">Admin</h1>
      <Tabs defaultValue="permissions">
        <Tabs.List>
          <Tabs.Tab value="permissions">Permissions</Tabs.Tab>
          <Tabs.Tab value="roles">Roles</Tabs.Tab>
          <Tabs.Tab value="users">Users</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="permissions" pt="md">
          <PermissionsTab />
        </Tabs.Panel>
        <Tabs.Panel value="roles" pt="md">
          <RolesTab />
        </Tabs.Panel>
        <Tabs.Panel value="users" pt="md">
          <UsersTab />
        </Tabs.Panel>
      </Tabs>
    </div>
  );
}

function PermissionsTab() {
  const { data } = usePermissions();
  const create = useCreatePermission();
  const update = useUpdatePermission();
  const del = useDeletePermission();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [editing, setEditing] = useState<Permission | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");

  async function onCreate() {
    try {
      await create.mutateAsync({ name, description });
      setName("");
      setDescription("");
    } catch {
      notifications.show({ message: "Failed to create permission", color: "red" });
    }
  }

  function openEdit(p: Permission) {
    setEditing(p);
    setEditName(p.name);
    setEditDescription(p.description ?? "");
  }

  async function onSaveEdit() {
    if (!editing) return;
    try {
      await update.mutateAsync({
        pid: editing.id,
        body: { name: editName, description: editDescription },
      });
      setEditing(null);
    } catch {
      notifications.show({ message: "Failed to update permission", color: "red" });
    }
  }

  return (
    <div>
      <div className="box">
        <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
        <Textarea
          label="Description"
          value={description}
          onChange={(e) => setDescription(e.currentTarget.value)}
        />
        <Button mt="md" onClick={onCreate} loading={create.isPending}>
          Create permission
        </Button>
      </div>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Name</Table.Th>
            <Table.Th>Description</Table.Th>
            <Table.Th>Actions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {(data ?? []).map((p) => (
            <Table.Tr key={p.id}>
              <Table.Td>{p.name}</Table.Td>
              <Table.Td>{p.description}</Table.Td>
              <Table.Td>
                <Button size="xs" onClick={() => openEdit(p)}>
                  Edit
                </Button>{" "}
                <Button size="xs" color="red" onClick={() => del.mutateAsync(p.id)}>
                  Delete
                </Button>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Modal opened={!!editing} onClose={() => setEditing(null)} title="Edit permission">
        <TextInput
          label="Name"
          value={editName}
          onChange={(e) => setEditName(e.currentTarget.value)}
        />
        <Textarea
          label="Description"
          value={editDescription}
          onChange={(e) => setEditDescription(e.currentTarget.value)}
        />
        <Button mt="md" onClick={onSaveEdit}>
          Save
        </Button>
      </Modal>
    </div>
  );
}
```
(Temporary `RolesTab`/`UsersTab` stubs returning `null` — filled in Tasks 6/7.)

- [ ] **Step 4: Add the route + nav**

`App.tsx`: import `AdminPage`; add `<Route path="admin" element={<AdminPage />} />` inside the `AppShell` route.
`AppShell.tsx`: import `Link` already; compute `const canAdmin = user?.permissions.some((p) => p === "roles:manage" || p === "users:manage");` and render the Admin link conditionally.

- [ ] **Step 5: Run tests + build + commit**

```powershell
Set-Location apps/web; bun run test AdminPage; bun run build
```
```bash
git add apps/web/src/pages/AdminPage.tsx apps/web/src/pages/AdminPage.test.tsx apps/web/src/App.tsx apps/web/src/components/layout/AppShell.tsx
git commit -m "feat(web): admin page shell + permissions tab"
```

---

### Task 6: Frontend — Roles tab

**Files:**
- Modify: `apps/web/src/pages/AdminPage.tsx`
- Modify: `apps/web/src/pages/AdminPage.test.tsx`

- [ ] **Step 1: Implement `RolesTab`**

Add imports: `Modal`, `MultiSelect` (Mantine); types `Role`; hooks `useCreateRole`, `useDeleteRole`, `useRolePermissions`, `useSetRolePermissions`, `useUpdateRole`. Replace the `RolesTab` stub with:
```tsx
function RolesTab() {
  const { data: roles } = useRoles();
  const { data: permissions } = usePermissions();
  const create = useCreateRole();
  const del = useDeleteRole();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [permRole, setPermRole] = useState<Role | null>(null);
  const [editRole, setEditRole] = useState<Role | null>(null);

  async function onCreate() {
    try {
      await create.mutateAsync({ name, description });
      setName("");
      setDescription("");
    } catch {
      notifications.show({ message: "Failed to create role", color: "red" });
    }
  }

  return (
    <div>
      <div className="box">
        <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
        <Textarea
          label="Description"
          value={description}
          onChange={(e) => setDescription(e.currentTarget.value)}
        />
        <Button mt="md" onClick={onCreate} loading={create.isPending}>
          Create role
        </Button>
      </div>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Name</Table.Th>
            <Table.Th>Description</Table.Th>
            <Table.Th>Actions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {(roles ?? []).map((r) => (
            <Table.Tr key={r.id}>
              <Table.Td>{r.name}</Table.Td>
              <Table.Td>{r.description}</Table.Td>
              <Table.Td>
                <Button size="xs" onClick={() => setEditRole(r)}>
                  Edit
                </Button>{" "}
                <Button size="xs" onClick={() => setPermRole(r)}>
                  Permissions
                </Button>{" "}
                <Button size="xs" color="red" onClick={() => del.mutateAsync(r.id)}>
                  Delete
                </Button>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {editRole && <RoleEditModal role={editRole} onClose={() => setEditRole(null)} />}
      {permRole && (
        <RolePermissionsModal
          role={permRole}
          permissions={permissions ?? []}
          onClose={() => setPermRole(null)}
        />
      )}
    </div>
  );
}

function RoleEditModal({ role, onClose }: { role: Role; onClose: () => void }) {
  const update = useUpdateRole();
  const [name, setName] = useState(role.name);
  const [description, setDescription] = useState(role.description ?? "");
  async function onSave() {
    await update.mutateAsync({ rid: role.id, body: { name, description } });
    onClose();
  }
  return (
    <Modal opened onClose={onClose} title="Edit role">
      <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
      <Textarea
        label="Description"
        value={description}
        onChange={(e) => setDescription(e.currentTarget.value)}
      />
      <Button mt="md" onClick={onSave}>
        Save
      </Button>
    </Modal>
  );
}

function RolePermissionsModal({
  role,
  permissions,
  onClose,
}: {
  role: Role;
  permissions: Permission[];
  onClose: () => void;
}) {
  const { data: current } = useRolePermissions(role.id);
  const save = useSetRolePermissions();
  const [selected, setSelected] = useState<string[] | null>(null);
  const value = selected ?? (current ?? []).map((p) => p.id);
  async function onSave() {
    await save.mutateAsync({ rid: role.id, ids: value });
    onClose();
  }
  return (
    <Modal opened onClose={onClose} title={`Permissions for ${role.name}`}>
      <MultiSelect
        label="Permissions"
        data={permissions.map((p) => ({ value: p.id, label: p.name }))}
        value={value}
        onChange={setSelected}
      />
      <Button mt="md" onClick={onSave}>
        Save
      </Button>
    </Modal>
  );
}
```

- [ ] **Step 2: Update the test**

Mock `useRoles` with one role, `usePermissions` with one permission; assert the role name renders. Keep it light (full assignment covered by E2E).

- [ ] **Step 3: Run + build + commit**

```powershell
Set-Location apps/web; bun run test AdminPage; bun run build
```
```bash
git add apps/web/src/pages/AdminPage.tsx apps/web/src/pages/AdminPage.test.tsx
git commit -m "feat(web): admin roles tab (permission assignment)"
```

---

### Task 7: Frontend — Users tab

**Files:**
- Modify: `apps/web/src/pages/AdminPage.tsx`
- Modify: `apps/web/src/pages/AdminPage.test.tsx`

- [ ] **Step 1: Implement `UsersTab`**

Add imports: `PasswordInput`, `Switch`, `MultiSelect`, `Modal` (Mantine); type `User`; hooks `useCreateUser`, `useDeleteUser`, `useSetUserRoles`, `useUpdateUser`, `useUserRoles` (plus `useRoles`, `useUsers` already imported). Replace the `UsersTab` stub with:
```tsx
function UsersTab() {
  const { data: users } = useUsers();
  const { data: roles } = useRoles();
  const create = useCreateUser();
  const del = useDeleteUser();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [editUser, setEditUser] = useState<User | null>(null);
  const [rolesUser, setRolesUser] = useState<User | null>(null);

  async function onCreate() {
    try {
      await create.mutateAsync({ username, email, password });
      setUsername("");
      setEmail("");
      setPassword("");
    } catch {
      notifications.show({ message: "Failed to create user", color: "red" });
    }
  }

  return (
    <div>
      <div className="box">
        <TextInput
          label="Username"
          value={username}
          onChange={(e) => setUsername(e.currentTarget.value)}
        />
        <TextInput label="Email" value={email} onChange={(e) => setEmail(e.currentTarget.value)} />
        <PasswordInput
          label="Password"
          value={password}
          onChange={(e) => setPassword(e.currentTarget.value)}
        />
        <Button mt="md" onClick={onCreate} loading={create.isPending}>
          Create user
        </Button>
      </div>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Username</Table.Th>
            <Table.Th>Email</Table.Th>
            <Table.Th>Active</Table.Th>
            <Table.Th>Actions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {(users ?? []).map((u) => (
            <Table.Tr key={u.id}>
              <Table.Td>{u.username}</Table.Td>
              <Table.Td>{u.email}</Table.Td>
              <Table.Td>{u.is_active ? "yes" : "no"}</Table.Td>
              <Table.Td>
                <Button size="xs" onClick={() => setEditUser(u)}>
                  Edit
                </Button>{" "}
                <Button size="xs" onClick={() => setRolesUser(u)}>
                  Roles
                </Button>{" "}
                <Button size="xs" color="red" onClick={() => del.mutateAsync(u.id)}>
                  Delete
                </Button>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {editUser && <UserEditModal user={editUser} onClose={() => setEditUser(null)} />}
      {rolesUser && (
        <UserRolesModal
          user={rolesUser}
          roles={roles ?? []}
          onClose={() => setRolesUser(null)}
        />
      )}
    </div>
  );
}

function UserEditModal({ user, onClose }: { user: User; onClose: () => void }) {
  const update = useUpdateUser();
  const [email, setEmail] = useState(user.email);
  const [isActive, setIsActive] = useState(user.is_active);
  const [password, setPassword] = useState("");
  async function onSave() {
    await update.mutateAsync({
      uid: user.id,
      body: { email, is_active: isActive, ...(password ? { password } : {}) },
    });
    onClose();
  }
  return (
    <Modal opened onClose={onClose} title="Edit user">
      <TextInput label="Email" value={email} onChange={(e) => setEmail(e.currentTarget.value)} />
      <Switch
        label="Active"
        checked={isActive}
        onChange={(e) => setIsActive(e.currentTarget.checked)}
      />
      <PasswordInput
        label="New password"
        value={password}
        onChange={(e) => setPassword(e.currentTarget.value)}
      />
      <Button mt="md" onClick={onSave}>
        Save
      </Button>
    </Modal>
  );
}

function UserRolesModal({
  user,
  roles,
  onClose,
}: {
  user: User;
  roles: Role[];
  onClose: () => void;
}) {
  const { data: current } = useUserRoles(user.id);
  const save = useSetUserRoles();
  const [selected, setSelected] = useState<string[] | null>(null);
  const value = selected ?? (current ?? []).map((r) => r.id);
  async function onSave() {
    await save.mutateAsync({ uid: user.id, ids: value });
    onClose();
  }
  return (
    <Modal opened onClose={onClose} title={`Roles for ${user.username}`}>
      <MultiSelect
        label="Roles"
        data={roles.map((r) => ({ value: r.id, label: r.name }))}
        value={value}
        onChange={setSelected}
      />
      <Button mt="md" onClick={onSave}>
        Save
      </Button>
    </Modal>
  );
}
```

- [ ] **Step 2: Update the test**

Mock `useUsers` with one user; assert the username renders.

- [ ] **Step 3: Run + build + commit**

```powershell
Set-Location apps/web; bun run test; bun run build
```
```bash
git add apps/web/src/pages/AdminPage.tsx apps/web/src/pages/AdminPage.test.tsx
git commit -m "feat(web): admin users tab (role assignment)"
```

---

### Task 8: E2E — RBAC end to end

**Files:**
- Create: `apps/web/e2e/rbac.spec.ts`

- [ ] **Step 1: Write the spec**

```ts
import { expect, test } from "@playwright/test";

const API = "http://localhost:8000";

test("admin grants a non-admin user a permission", async ({ page, request }) => {
  const suffix = Date.now();
  const roleName = `e2e-role-${suffix}`;
  const userName = `e2e-user-${suffix}`;

  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("admin");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();

  await page.getByRole("link", { name: "Admin" }).click();

  // Permissions tab: create a probe permission (projects:read is pre-seeded by dev_seed)
  const probe = `e2e:probe-${suffix}`;
  await page.getByRole("tab", { name: "Permissions" }).click();
  await page.getByLabel("Name").fill(probe);
  await page.getByRole("button", { name: "Create permission" }).click();

  // Roles tab: create role + grant the pre-seeded projects:read permission
  await page.getByRole("tab", { name: "Roles" }).click();
  await page.getByLabel("Name").fill(roleName);
  await page.getByRole("button", { name: "Create role" }).click();
  const roleRow = page.getByRole("row", { name: new RegExp(roleName) });
  await roleRow.getByRole("button", { name: "Permissions" }).click();
  await page.getByLabel("Permissions").click();
  await page.getByRole("option", { name: "projects:read" }).click();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Save" }).click();

  // Users tab: create user + assign role
  await page.getByRole("tab", { name: "Users" }).click();
  await page.getByLabel("Username").fill(userName);
  await page.getByLabel("Email").fill(`${userName}@x`);
  await page.getByLabel("Password").fill("pw");
  await page.getByRole("button", { name: "Create user" }).click();
  const userRow = page.getByRole("row", { name: new RegExp(userName) });
  await userRow.getByRole("button", { name: "Roles" }).click();
  await page.getByLabel("Roles").click();
  await page.getByRole("option", { name: roleName }).click();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Save" }).click();

  // The non-admin user can read projects but cannot create agents.
  const login = await request.post(`${API}/auth/login`, {
    data: { username: userName, password: "pw" },
  });
  const token = (await login.json()).access_token;
  const h = { Authorization: `Bearer ${token}` };
  expect((await request.get(`${API}/projects`, { headers: h })).status()).toBe(200);
  const denied = await request.post(`${API}/agents`, {
    headers: h,
    data: { name: "x", model: "test-model" },
  });
  expect(denied.status()).toBe(403);
});
```

- [ ] **Step 2: Run E2E**

```powershell
Set-Location apps/web; bun run e2e
```
Expected: all specs pass.

- [ ] **Step 3: Commit**

```bash
git add apps/web/e2e/rbac.spec.ts
git commit -m "test(web): E2E RBAC admin grants permission to a user"
```

---

## Notes

- `POST /roles` already exists (name/description); the Roles tab needs a `createRole` helper/hook (add it in Task 4).
- The `Permissions` tab's Edit uses `window.prompt` in Task 5 as a minimal step; replace with a Mantine `Modal` if desired (test unaffected).
- The E2E assumes `admin` (all permissions). If `projects:read` already exists, the create call logs a 409 notification; the role assignment still works.
- Keep `ruff`/`ty`/`bandit` clean; regenerate `schema.d.ts` after backend changes (Task 3).
