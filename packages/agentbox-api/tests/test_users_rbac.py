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
        await s.flush()
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r1", name="admin"))
        s.add(Permission(id="perm1", name="users:manage"))
        await s.flush()
        s.add(RolePermissionLink(role_id="r1", permission_id="perm1"))
        await s.flush()
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(Role(id="r2", name="viewer"))
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
        r = await client.put(f"/users/{uid}", json={"is_active": False}, headers=h)
        assert r.json()["is_active"] is False
        r = await client.put(
            f"/users/{uid}/roles", json={"role_ids": ["r2"]}, headers=h
        )
        assert r.status_code == 200
        r = await client.get(f"/users/{uid}/roles", headers=h)
        assert [x["name"] for x in r.json()] == ["viewer"]
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
            "/users",
            json={"username": "bob", "email": "b@x", "password": "pw"},
            headers=h,
        )
        uid = r.json()["id"]
        await client.put(f"/users/{uid}/roles", json={"role_ids": ["r2"]}, headers=h)
        async with factory() as s:
            await s.flush()
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


async def test_update_user_rejects_blank_password_and_preserves_value():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        r = await client.post(
            "/users",
            json={"username": "bob", "email": "b@x", "password": "pw"},
            headers=h,
        )
        uid = r.json()["id"]

        r = await client.put(f"/users/{uid}", json={"password": "   "}, headers=h)
        assert r.status_code == 422

        r = await client.put(f"/users/{uid}", json={"password": " new "}, headers=h)
        assert r.status_code == 200
        async with factory() as s:
            user = await s.get(User, uid)
        assert verify_password(" new ", user.password_hash)
        assert not verify_password("new", user.password_hash)
    finally:
        await client.aclose()
        await engine.dispose()
