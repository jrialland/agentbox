import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import Permission, Role, RolePermissionLink, User, UserRoleLink


async def _seed_user(factory, user_id: str, username: str, perms: list[str]):
    async with factory() as s:
        s.add(
            User(
                id=user_id,
                username=username,
                email=f"{username}@x",
                password_hash=hash_password("pw"),
            )
        )
        s.add(Role(id=f"r_{user_id}", name="role"))
        for i, p in enumerate(perms):
            s.add(Permission(id=f"p{i}_{user_id}", name=p))
            s.add(RolePermissionLink(role_id=f"r_{user_id}", permission_id=f"p{i}_{user_id}"))
        s.add(UserRoleLink(user_id=user_id, role_id=f"r_{user_id}"))
        await s.commit()


async def _make_app(perms: list[str]):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    await _seed_user(factory, "u1", "alice", perms)
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return engine, client


async def _login(client) -> str:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return r.json()["access_token"]


async def test_providers_create_and_list():
    engine, client = await _make_app(["providers:create", "providers:read"])
    try:
        token = await _login(client)
        r = await client.post(
            "/providers",
            json={"id": "p1", "name": "openai", "kind": "generic"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        r = await client.get("/providers", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert any(p["id"] == "p1" for p in r.json())
    finally:
        await client.aclose()
        await engine.dispose()


async def test_providers_requires_permission():
    engine, client = await _make_app([])
    try:
        r = await client.get("/providers")
        assert r.status_code in (401, 403)
    finally:
        await client.aclose()
        await engine.dispose()


async def test_projects_create_and_list():
    engine, client = await _make_app(["projects:create", "projects:read"])
    try:
        token = await _login(client)
        r = await client.post(
            "/projects",
            json={"id": "prj1", "name": "myproj", "path": "/tmp/p", "owner_id": "u1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        r = await client.get("/projects", headers={"Authorization": f"Bearer {token}"})
        assert any(p["id"] == "prj1" for p in r.json())
    finally:
        await client.aclose()
        await engine.dispose()


async def test_sessions_create_and_list():
    engine, client = await _make_app(["sessions:create", "sessions:read"])
    try:
        token = await _login(client)
        r = await client.post(
            "/sessions",
            json={"id": "s1", "project_id": "prj", "agent_id": "ag"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        r = await client.get("/sessions", headers={"Authorization": f"Bearer {token}"})
        assert any(s["id"] == "s1" for s in r.json())
    finally:
        await client.aclose()
        await engine.dispose()
