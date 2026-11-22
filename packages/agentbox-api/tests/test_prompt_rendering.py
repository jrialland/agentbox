import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_api.skills import prepare_agent
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import (
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)
from agentbox_models.tables.core import Agent, Model, Provider


async def _setup(instructions: str):
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
        for i, permission in enumerate(
            (
                "sessions:create",
                "sessions:read",
                "agents:create",
                "agents:read",
                "projects:create",
            )
        ):
            s.add(Permission(id=f"p{i}", name=permission))
            await s.flush()
            s.add(RolePermissionLink(role_id="r1", permission_id=f"p{i}"))
        await s.flush()
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(Provider(id="prov", name="prov", kind="test"))
        await s.flush()
        s.add(Model(id="m1", provider_id="prov", name="test-model"))
        await s.flush()
        s.add(
            Agent(
                id="ag",
                name="bot",
                description="d",
                instructions=instructions,
                model_id="m1",
            )
        )
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


async def test_prepare_agent_renders_before_skill_catalog(tmp_path):
    engine, _, factory = await _setup("Hello {{ user.username }}")
    try:
        prepared = await prepare_agent(
            factory,
            "bot",
            str(tmp_path),
            str(tmp_path / "skills"),
            user_name="alice",
        )
        assert prepared.spec.instructions.startswith("Hello alice")
    finally:
        await engine.dispose()


async def test_chat_rejects_broken_template():
    engine, client, _ = await _setup("{% if %}")
    try:
        h = await _auth(client)
        project = await client.post(
            "/projects", json={"name": "p", "path": "."}, headers=h
        )
        session = await client.post(
            "/sessions",
            json={"project_id": project.json()["id"], "agent_id": "bot"},
            headers=h,
        )
        r = await client.post(
            f"/sessions/{session.json()['id']}/messages",
            json={"content": "hi", "mode": "agent"},
            headers=h,
        )
        assert r.status_code == 422
        detail = r.json()["detail"].lower()
        assert "expected an expression" in detail or "end of statement" in detail
    finally:
        await client.aclose()
        await engine.dispose()
