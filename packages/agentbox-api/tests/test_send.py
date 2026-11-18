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
from agentbox_models.tables.core import Agent, Model, Project, Provider, SessionRow


async def _setup(tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r_u1", name="role"))
        for i, p in enumerate(["sessions:create", "sessions:read"]):
            s.add(Permission(id=f"p{i}_u1", name=p))
            s.add(RolePermissionLink(role_id="r_u1", permission_id=f"p{i}_u1"))
        s.add(UserRoleLink(user_id="u1", role_id="r_u1"))
        s.add(Provider(id="prov", name="test", kind="test"))
        s.add(Model(id="m", provider_id="prov", name="test-model"))
        s.add(
            Agent(
                id="ag",
                name="agent",
                description="d",
                instructions="i",
                model_id="m",
                tool_bindings="[]",
                mode_definitions='[{"name":"ask","flags":{"write":false}},{"name":"agent","flags":{"write":true}}]',
                sub_agent_ids="[]",
            )
        )
        s.add(Project(id="prj", name="p", path=str(tmp_path), owner_id="u1"))
        s.add(SessionRow(id="s1", project_id="prj", agent_id="ag"))
        await s.commit()
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return engine, client, factory


async def _login(client) -> str:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return r.json()["access_token"]


async def test_test_provider_resolves():
    from agentbox_providers.resolver import resolve_model

    model = resolve_model(Provider(id="x", name="t", kind="test"), "whatever")
    assert model is not None


async def test_send_records_turns_and_forks(tmp_path):
    engine, client, factory = await _setup(tmp_path)
    try:
        token = await _login(client)
        h = {"Authorization": f"Bearer {token}"}

        r = await client.post(
            "/sessions/s1/messages", json={"content": "hi"}, headers=h
        )
        assert r.status_code == 200

        r = await client.get("/sessions/s1/messages", headers=h)
        msgs = r.json()
        assert [m["role"] for m in msgs] == ["user", "assistant"]
        user_turn = msgs[0]["id"]

        # fork from the first user turn
        r = await client.post(
            "/sessions/s1/messages",
            json={
                "content": "edited",
                "fork": True,
                "fork_from_turn_id": user_turn,
                "mode": "ask",
            },
            headers=h,
        )
        assert r.status_code == 200

        r = await client.get("/sessions/s1/messages", headers=h)
        branch = r.json()
        assert branch[0]["id"] == user_turn
        assert branch[-1]["role"] == "assistant"
        assert len(branch) == 3
    finally:
        await client.aclose()
        await engine.dispose()


async def test_send_with_attachment(tmp_path):
    engine, client, factory = await _setup(tmp_path)
    try:
        token = await _login(client)
        h = {"Authorization": f"Bearer {token}"}
        up = await client.post(
            "/sessions/s1/attachments",
            files={"file": ("n.txt", b"data", "text/plain")},
            headers=h,
        )
        att_id = up.json()["id"]
        r = await client.post(
            "/sessions/s1/messages",
            json={"content": "see file", "attachment_ids": [att_id]},
            headers=h,
        )
        assert r.status_code == 200
    finally:
        await client.aclose()
        await engine.dispose()
