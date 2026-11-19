import httpx
from loguru import logger

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import User


class Capture:
    def __init__(self):
        self.messages: list[str] = []
        self._id = None

    def __enter__(self):
        self._id = logger.add(self.messages.append, level="DEBUG", format="{message}")
        return self

    def __exit__(self, *exc):
        if self._id is not None:
            logger.remove(self._id)

    def text(self) -> str:
        return "\n".join(self.messages)


async def _app_with_user(username="alice", password="secret"):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            User(
                id="u1",
                username=username,
                email=f"{username}@x",
                password_hash=hash_password(password),
            )
        )
        await s.commit()
    app = create_app(
        Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    return engine, client


async def test_login_logs_success_without_password():
    engine, client = await _app_with_user()
    try:
        with Capture() as cap:
            r = await client.post(
                "/auth/login", json={"username": "alice", "password": "secret"}
            )
        assert r.status_code == 200
        text = cap.text()
        assert "login ok" in text
        assert "user=alice" in text
        assert "secret" not in text
    finally:
        await client.aclose()
        await engine.dispose()


async def test_login_failure_logs_warning():
    engine, client = await _app_with_user()
    try:
        with Capture() as cap:
            r = await client.post(
                "/auth/login", json={"username": "alice", "password": "wrong"}
            )
        assert r.status_code == 401
        assert "login failed" in cap.text()
        assert "user=alice" in cap.text()
        assert "wrong" not in cap.text()
    finally:
        await client.aclose()
        await engine.dispose()
