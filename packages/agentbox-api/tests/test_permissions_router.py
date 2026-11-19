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


async def _setup(perms=("roles:manage",)):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r1", name="admin"))
        for i, p in enumerate(perms):
            s.add(Permission(id=f"p{i}", name=p))
            s.add(RolePermissionLink(role_id="r1", permission_id=f"p{i}"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        await s.commit()
    app = create_app(
        Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
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
