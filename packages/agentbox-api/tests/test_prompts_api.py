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


async def _client():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        await s.flush()
        s.add(
            User(
                id="u1",
                username="alice",
                email="a@x",
                password_hash=hash_password("pw"),
            )
        )
        s.add(Role(id="r1", name="role"))
        s.add(Permission(id="p0", name="agents:create"))
        await s.flush()
        s.add(RolePermissionLink(role_id="r1", permission_id="p0"))
        await s.flush()
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        await s.commit()
    app = create_app(
        Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    return engine, client


async def test_preview_returns_rendered_and_context():
    engine, client = await _client()
    try:
        r = await client.post(
            "/auth/login", json={"username": "alice", "password": "pw"}
        )
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        r = await client.post(
            "/prompts/preview",
            json={
                "template": "Hi {{ user.username }}",
                "context": {"user.username": "bob"},
            },
            headers=h,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["rendered"] == "Hi bob"
        assert body["error"] is None
        assert body["context"]["user.username"] == "bob"
        assert "project.path" in body["variables"]
    finally:
        await client.aclose()
        await engine.dispose()
