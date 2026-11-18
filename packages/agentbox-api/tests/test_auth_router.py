import httpx

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


async def test_login():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw")))
        await s.commit()

    app = create_app(
        Settings(jwt_secret="s" * 32, database_url="sqlite+aiosqlite:///:memory:"),
        engine=engine,
        session_factory=factory,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
        assert r.status_code == 200
        assert "access_token" in r.json()
    await engine.dispose()


async def test_login_wrong_password():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw")))
        await s.commit()

    app = create_app(
        Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/auth/login", json={"username": "alice", "password": "bad"})
        assert r.status_code == 401
    await engine.dispose()


async def test_me_requires_auth():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/auth/me")
        assert r.status_code == 401
    await engine.dispose()


async def test_me_returns_user_and_permissions():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw")))
        s.add(Role(id="r1", name="admin"))
        s.add(Permission(id="perm1", name="agents:read"))
        s.add(RolePermissionLink(role_id="r1", permission_id="perm1"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        await s.commit()

    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
        token = login.json()["access_token"]
        r = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["username"] == "alice"
        assert "agents:read" in body["permissions"]
    await engine.dispose()
