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


async def _setup(perms=("providers:create", "providers:read", "providers:delete")):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r1", name="role"))
        for i, p in enumerate(perms):
            s.add(Permission(id=f"p{i}", name=p))
            s.add(RolePermissionLink(role_id="r1", permission_id=f"p{i}"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(Provider(id="prov", name="old", kind="generic", api_key="secret"))
        s.add(Model(id="m1", provider_id="prov", name="m"))
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


async def test_provider_update_preserves_api_key_when_omitted():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        r = await client.put("/providers/prov", json={"name": "new"}, headers=h)
        assert r.json()["name"] == "new"
        async with factory() as s:
            assert (await s.get(Provider, "prov")).api_key == "secret"
    finally:
        await client.aclose()
        await engine.dispose()


async def test_provider_delete_blocked_when_model_in_use():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        async with factory() as s:
            s.add(Agent(id="ag", name="a", description="", instructions="", model_id="m1"))
            await s.commit()
        r = await client.delete("/providers/prov", headers=h)
        assert r.status_code == 409
    finally:
        await client.aclose()
        await engine.dispose()


async def test_provider_delete_cascades_models():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        r = await client.delete("/providers/prov", headers=h)
        assert r.status_code == 200
        async with factory() as s:
            assert await s.get(Provider, "prov") is None
            assert await s.get(Model, "m1") is None
    finally:
        await client.aclose()
        await engine.dispose()
