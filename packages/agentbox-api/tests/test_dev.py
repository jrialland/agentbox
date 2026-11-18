import httpx
from sqlmodel import select

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.dev_seed import seed_admin
from agentbox_api.security import verify_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import User


async def test_cors_allows_frontend_origin():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/openapi.json", headers={"Origin": "http://localhost:5173"})
        assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    await engine.dispose()


async def test_seed_admin_idempotent():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    await seed_admin(factory)
    await seed_admin(factory)
    async with factory() as s:
        users = (
            await s.execute(select(User).where(User.username == "admin"))
        ).scalars().all()
        assert len(users) == 1
        assert verify_password("admin", users[0].password_hash)
    await engine.dispose()
