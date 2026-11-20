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


async def test_messages_stop_at_summary():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r1", name="role"))
        s.add(Permission(id="perm", name="sessions:read"))
        s.add(RolePermissionLink(role_id="r1", permission_id="perm"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        for row in (
            TurnRow(id="t1", session_id="s1", role="user", content="old question"),
            TurnRow(
                id="t2",
                session_id="s1",
                role="assistant",
                content="old answer",
                parent_id="t1",
            ),
            TurnRow(id="sum", session_id="s1", role="summary", content="summary"),
            TurnRow(
                id="t3",
                session_id="s1",
                role="user",
                content="new question",
                parent_id="sum",
            ),
            TurnRow(
                id="t4",
                session_id="s1",
                role="assistant",
                content="new answer",
                parent_id="t3",
            ),
        ):
            s.add(row)
        await s.commit()

    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    try:
        login = await client.post(
            "/auth/login", json={"username": "alice", "password": "pw"}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        response = await client.get("/sessions/s1/messages", headers=headers)
        assert response.status_code == 200
        assert [(m["id"], m["role"]) for m in response.json()] == [
            ("sum", "summary"),
            ("t3", "user"),
            ("t4", "assistant"),
        ]
    finally:
        await client.aclose()
        await engine.dispose()
