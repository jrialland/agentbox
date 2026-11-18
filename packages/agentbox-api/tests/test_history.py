from datetime import UTC, datetime, timedelta

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
from agentbox_models.tables.core import TurnRow


async def _make_app(perms: list[str]):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r_u1", name="role"))
        for i, p in enumerate(perms):
            s.add(Permission(id=f"p{i}_u1", name=p))
            s.add(RolePermissionLink(role_id="r_u1", permission_id=f"p{i}_u1"))
        s.add(UserRoleLink(user_id="u1", role_id="r_u1"))
        await s.commit()
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return engine, client, factory


async def _login(client) -> str:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return r.json()["access_token"]


def _at(base: datetime, seconds: int) -> datetime:
    return base + timedelta(seconds=seconds)


async def test_history_active_branch():
    engine, client, factory = await _make_app(["sessions:read"])
    base = datetime(2026, 1, 1, tzinfo=UTC)
    try:
        async with factory() as s:
            turns = [
                TurnRow(
                    id="t1",
                    session_id="s1",
                    role="user",
                    content="q1",
                    parent_id=None,
                    created_at=_at(base, 0),
                ),
                TurnRow(
                    id="t2",
                    session_id="s1",
                    role="assistant",
                    content="a1",
                    parent_id="t1",
                    created_at=_at(base, 1),
                ),
                TurnRow(
                    id="t3",
                    session_id="s1",
                    role="assistant",
                    content="a2",
                    parent_id="t1",
                    created_at=_at(base, 2),
                ),
            ]
            for t in turns:
                s.add(t)
            await s.commit()

        token = await _login(client)
        r = await client.get(
            "/sessions/s1/messages", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        assert [m["id"] for m in r.json()] == ["t1", "t3"]
    finally:
        await client.aclose()
        await engine.dispose()
