import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import Permission, Role, RolePermissionLink, User, UserRoleLink


async def _make_app(perms: list[str]):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw")))
        s.add(Role(id="r1", name="admin"))
        for i, p in enumerate(perms):
            s.add(Permission(id=f"perm{i}", name=p))
            s.add(RolePermissionLink(role_id="r1", permission_id=f"perm{i}"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        await s.commit()
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return engine, client


async def _login(client) -> str:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return r.json()["access_token"]


async def test_users_requires_admin():
    engine, client = await _make_app([])
    try:
        r = await client.get("/users")
        assert r.status_code in (401, 403)
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_and_list_user():
    engine, client = await _make_app(["users:manage"])
    try:
        token = await _login(client)
        h = {"Authorization": f"Bearer {token}"}
        r = await client.post(
            "/users", json={"username": "bob", "email": "b@x", "password": "pw"}, headers=h
        )
        assert r.status_code == 200
        r = await client.get("/users", headers=h)
        assert any(u["username"] == "bob" for u in r.json())
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_api_key_returns_secret():
    engine, client = await _make_app(["api_keys:manage"])
    try:
        token = await _login(client)
        h = {"Authorization": f"Bearer {token}"}
        r = await client.post("/api-keys", json={"scopes": ["agents:read"]}, headers=h)
        assert r.status_code == 200
        assert "key" in r.json()
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_role():
    engine, client = await _make_app(["roles:manage"])
    try:
        token = await _login(client)
        h = {"Authorization": f"Bearer {token}"}
        r = await client.post("/roles", json={"name": "editor"}, headers=h)
        assert r.status_code == 200
        r = await client.get("/roles", headers=h)
        assert any(x["name"] == "editor" for x in r.json())
    finally:
        await client.aclose()
        await engine.dispose()
