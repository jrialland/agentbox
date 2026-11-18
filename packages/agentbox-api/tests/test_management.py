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


async def _seed_user(factory, user_id: str, username: str, perms: list[str]):
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
            s.add(
                RolePermissionLink(
                    role_id=f"r_{user_id}", permission_id=f"p{i}_{user_id}"
                )
            )
        s.add(UserRoleLink(user_id=user_id, role_id=f"r_{user_id}"))
        await s.commit()


async def _make_app(perms: list[str]):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    await _seed_user(factory, "u1", "alice", perms)
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return engine, client


async def _login(client) -> str:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return r.json()["access_token"]


async def _async(value):
    return value


async def test_provider_read_omits_api_key():
    engine, client = await _make_app(["providers:create", "providers:read"])
    try:
        token = await _login(client)
        h = {"Authorization": f"Bearer {token}"}
        r = await client.post(
            "/providers",
            json={"name": "openai", "kind": "generic", "api_key": "sk-secret"},
            headers=h,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["id"]
        assert "api_key" not in body
        r = await client.get("/providers", headers=h)
        assert all("api_key" not in p for p in r.json())
    finally:
        await client.aclose()
        await engine.dispose()


async def test_refresh_persists_and_dedupes(monkeypatch):
    monkeypatch.setattr(
        "agentbox_api.routers.providers.list_models",
        lambda provider: _async(["m1", "m2"]),
    )
    engine, client = await _make_app(
        ["providers:create", "providers:read", "providers:list-models"]
    )
    try:
        token = await _login(client)
        h = {"Authorization": f"Bearer {token}"}
        r = await client.post(
            "/providers",
            json={"name": "p", "kind": "generic", "models_url": "http://x"},
            headers=h,
        )
        pid = r.json()["id"]
        r = await client.post(f"/providers/{pid}/models/refresh", headers=h)
        assert {m["name"] for m in r.json()} == {"m1", "m2"}
        r = await client.post(f"/providers/{pid}/models/refresh", headers=h)
        assert len(r.json()) == 2
        r = await client.get("/models", headers=h)
        assert len(r.json()) == 2
    finally:
        await client.aclose()
        await engine.dispose()
