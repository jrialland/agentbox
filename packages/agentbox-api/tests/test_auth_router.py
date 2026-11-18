import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import User


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
