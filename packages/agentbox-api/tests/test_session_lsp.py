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
from agentbox_models.tables.core import Agent, Model, Provider


async def _setup(project_path: str):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
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
            ("sessions:create", "sessions:read", "projects:create")
        ):
            s.add(Permission(id=f"p{i}", name=permission))
            s.add(RolePermissionLink(role_id="r1", permission_id=f"p{i}"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(Provider(id="prov", name="prov", kind="test"))
        s.add(Model(id="m1", provider_id="prov", name="test-model"))
        s.add(
            Agent(
                id="ag",
                name="bot",
                description="d",
                instructions="i",
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
    return engine, client


async def _auth(client) -> dict:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_session_lsp_lists_detected_stacks(tmp_path):
    (tmp_path / "a.py").write_text("x = 1", encoding="utf-8")
    engine, client = await _setup(str(tmp_path))
    try:
        h = await _auth(client)
        project = await client.post(
            "/projects", json={"name": "p", "path": str(tmp_path)}, headers=h
        )
        session = await client.post(
            "/sessions",
            json={"project_id": project.json()["id"], "agent_id": "bot"},
            headers=h,
        )
        r = await client.get(
            f"/sessions/{session.json()['id']}/lsp", headers=h
        )
        assert r.status_code == 200
        body = r.json()
        assert "python" in body["detected"]
        assert body["active"] == []
    finally:
        await client.aclose()
        await engine.dispose()
