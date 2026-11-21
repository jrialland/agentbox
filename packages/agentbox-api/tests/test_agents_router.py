import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import Permission, Role, RolePermissionLink, User, UserRoleLink
from agentbox_models.tables.core import Model, Provider


async def _seed_user_with_perms(factory, user_id: str, username: str, perms: list[str]):
    async with factory() as s:
        s.add(
            User(
                id=user_id,
                username=username,
                email=f"{username}@x",
                password_hash=hash_password("pw"),
            )
        )
        s.add(Role(id=f"r_{user_id}", name="role"))
        for i, p in enumerate(perms):
            s.add(Permission(id=f"p{i}_{user_id}", name=p))
            s.add(RolePermissionLink(role_id=f"r_{user_id}", permission_id=f"p{i}_{user_id}"))
        s.add(UserRoleLink(user_id=user_id, role_id=f"r_{user_id}"))
        await s.commit()


async def _login(client, username: str) -> str:
    r = await client.post("/auth/login", json={"username": username, "password": "pw"})
    assert r.status_code == 200
    return r.json()["access_token"]


async def test_create_agent_requires_permission():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/agents", json={"name": "coder"})
        assert r.status_code in (401, 403)
    await engine.dispose()


async def test_create_and_list_agent():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(Provider(id="p1", name="test", kind="generic"))
        s.add(Model(id="m1", provider_id="p1", name="test-model"))
        await s.commit()
    await _seed_user_with_perms(factory, "u1", "alice", ["agents:create", "agents:read"])

    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _login(client, "alice")
        r = await client.post(
            "/agents",
            json={"name": "coder", "model": "test-model"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        r = await client.get("/agents", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        names = [a["name"] for a in r.json()]
        assert "coder" in names
    await engine.dispose()

async def _agent_client():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(Provider(id="p1", name="test", kind="generic"))
        s.add(Model(id="m1", provider_id="p1", name="test-model"))
        await s.commit()
    await _seed_user_with_perms(factory, "u1", "alice", ["agents:create", "agents:read"])
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return engine, client


async def test_update_agent_round_trips_stdio_binding():
    engine, client = await _agent_client()
    try:
        token = await _login(client, "alice")
        h = {"Authorization": f"Bearer {token}"}
        r = await client.post(
            "/agents",
            json={"name": "coder", "model": "test-model"},
            headers=h,
        )
        assert r.status_code == 200

        binding = {
            "id": "time",
            "command": "uvx",
            "args": ["mcp-server-time"],
            "env": {"TZ": "UTC"},
            "env_passthrough": ["PATH"],
            "cwd": "sub",
        }
        r = await client.put(
            "/agents/coder",
            json={
                "name": "coder",
                "model": "test-model",
                "tool_bindings": [binding],
            },
            headers=h,
        )
        assert r.status_code == 200
        saved = r.json()["tool_bindings"][0]
        assert saved["id"] == "time"
        assert saved["command"] == "uvx"
        assert saved["cwd"] == "sub"
        assert saved["env_passthrough"] == ["PATH"]

        r = await client.get("/agents/coder", headers=h)
        assert r.json()["tool_bindings"][0]["command"] == "uvx"
    finally:
        await client.aclose()
        await engine.dispose()


async def test_rejects_invalid_stdio_bindings():
    engine, client = await _agent_client()
    try:
        token = await _login(client, "alice")
        h = {"Authorization": f"Bearer {token}"}
        cases = [
            {
                "name": "both",
                "model": "test-model",
                "tool_bindings": [
                    {"id": "x", "command": "python", "server_url": "http://x"}
                ],
            },
            {
                "name": "missing-id",
                "model": "test-model",
                "tool_bindings": [{"command": "python"}],
            },
            {
                "name": "dupe",
                "model": "test-model",
                "tool_bindings": [
                    {"id": "x", "command": "python"},
                    {"id": "x", "command": "python"},
                ],
            },
            {
                "name": "bad-env",
                "model": "test-model",
                "tool_bindings": [
                    {"id": "x", "command": "python", "env_passthrough": ["NOT-A-NAME"]}
                ],
            },
        ]
        for body in cases:
            r = await client.post("/agents", json=body, headers=h)
            assert r.status_code == 400, body["name"]
    finally:
        await client.aclose()
        await engine.dispose()
