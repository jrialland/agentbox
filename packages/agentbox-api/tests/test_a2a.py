import json

import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_api_key, hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import (
    ApiKey,
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)
from agentbox_models.tables.core import Agent, Model, Provider


async def _setup():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r1", name="role"))
        for i, p in enumerate(["agents:create", "agents:read"]):
            s.add(Permission(id=f"p{i}", name=p))
            s.add(RolePermissionLink(role_id="r1", permission_id=f"p{i}"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(
            ApiKey(
                id="k1",
                user_id="u1",
                key_hash=hash_api_key("testkey"),
                scopes=json.dumps(["sessions:create"]),
            )
        )
        s.add(Provider(id="prov", name="test", kind="test"))
        s.add(Model(id="m", provider_id="prov", name="test-model"))
        s.add(Agent(id="ag", name="bot", description="d", instructions="i", model_id="m"))
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


async def test_agent_card_crud():
    engine, client = await _setup()
    try:
        h = await _auth(client)
        assert (await client.get("/agents/bot/card", headers=h)).status_code == 404
        r = await client.put(
            "/agents/bot/card",
            json={"name": "Bot", "description": "d", "version": "1.0.0", "skills": []},
            headers=h,
        )
        assert r.status_code == 200
        assert (await client.get("/agents/bot/card", headers=h)).json()["name"] == "Bot"
        assert (await client.delete("/agents/bot/card", headers=h)).status_code == 200
        assert (await client.get("/agents/bot/card", headers=h)).status_code == 404
    finally:
        await client.aclose()
        await engine.dispose()


async def test_a2a_requires_api_key_and_discovers_card():
    engine, client = await _setup()
    try:
        assert (
            await client.get("/a2a/bot/.well-known/agent-card.json")
        ).status_code == 401
        h = await _auth(client)
        await client.put(
            "/agents/bot/card",
            json={"name": "Bot", "description": "d", "version": "1.0.0", "skills": []},
            headers=h,
        )
        assert (
            await client.get("/a2a/bot/.well-known/agent-card.json", headers=h)
        ).status_code == 403
        key_h = {"Authorization": "Bearer testkey"}
        r = await client.get("/a2a/bot/.well-known/agent-card.json", headers=key_h)
        assert r.status_code == 200
        assert r.json()["name"] == "Bot"
    finally:
        await client.aclose()
        await engine.dispose()
