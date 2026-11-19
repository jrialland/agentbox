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
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r1", name="admin"))
        s.add(Permission(id="perm1", name="roles:manage"))
        s.add(RolePermissionLink(role_id="r1", permission_id="perm1"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(Role(id="r2", name="viewer"))
        s.add(Permission(id="perm2", name="projects:read"))
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


async def test_role_update_and_assignment():
    engine, client, _ = await _setup()
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
        async with factory() as s:
            s.add(RolePermissionLink(role_id="r2", permission_id="perm2"))
            s.add(UserRoleLink(user_id="u1", role_id="r2"))
            await s.commit()
        await client.delete("/roles/r2", headers=h)
        async with factory() as s:
            links = (
                await s.execute(
                    select(RolePermissionLink).where(RolePermissionLink.role_id == "r2")
                )
            ).scalars().all()
            user_links = (
                await s.execute(
                    select(UserRoleLink).where(UserRoleLink.role_id == "r2")
                )
            ).scalars().all()
        assert links == [] and user_links == []
    finally:
        await client.aclose()
        await engine.dispose()
