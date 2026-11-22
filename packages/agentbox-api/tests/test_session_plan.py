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
from agentbox_models.tables.core import Agent, Model, PlanItem, Provider


async def _setup():
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
            ("sessions:create", "sessions:read", "projects:create")
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
    return engine, client, factory


async def _session(client, headers, tmp_path) -> str:
    project = await client.post(
        "/projects", json={"name": "p", "path": str(tmp_path)}, headers=headers
    )
    session = await client.post(
        "/sessions",
        json={"project_id": project.json()["id"], "agent_id": "bot"},
        headers=headers,
    )
    return session.json()["id"]


async def _auth(client) -> dict:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_plan_endpoint_orders_items(tmp_path):
    engine, client, factory = await _setup()
    try:
        headers = await _auth(client)
        sid = await _session(client, headers, tmp_path)
        async with factory() as s:
            await s.flush()
            s.add(PlanItem(id="b", session_id=sid, position=1, content="second"))
            await s.flush()
            s.add(
                PlanItem(
                    id="a",
                    session_id=sid,
                    position=0,
                    content="first",
                    status="completed",
                )
            )
            await s.commit()
        r = await client.get(f"/sessions/{sid}/plan", headers=headers)
        assert r.status_code == 200
        items = r.json()["items"]
        assert [item["id"] for item in items] == ["a", "b"]
        assert items[0]["content"] == "first"
        assert items[0]["status"] == "completed"
    finally:
        await client.aclose()
        await engine.dispose()


async def test_plan_endpoint_unknown_session(tmp_path):
    engine, client, _ = await _setup()
    try:
        headers = await _auth(client)
        r = await client.get("/sessions/missing/plan", headers=headers)
        assert r.status_code == 404
    finally:
        await client.aclose()
        await engine.dispose()
