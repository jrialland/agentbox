import httpx
from sqlmodel import func, select

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
from agentbox_models.tables.core import Provider


async def _app_with_provider_create():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as session:
        session.add(
            User(
                id="u1",
                username="alice",
                email="a@x",
                password_hash=hash_password("pw"),
            )
        )
        session.add(Role(id="r1", name="role"))
        session.add(Permission(id="p1", name="providers:create"))
        session.add(RolePermissionLink(role_id="r1", permission_id="p1"))
        session.add(UserRoleLink(user_id="u1", role_id="r1"))
        await session.commit()
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    token = (
        await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    ).json()["access_token"]
    return engine, factory, client, {"Authorization": f"Bearer {token}"}


async def test_provider_test_returns_models_without_persisting(monkeypatch):
    captured = {}

    async def fake_list_models(provider):
        captured["kind"] = provider.kind
        captured["key"] = provider.api_key
        return ["alpha", "beta", "gamma"]

    monkeypatch.setattr("agentbox_api.routers.providers.list_models", fake_list_models)
    engine, factory, client, headers = await _app_with_provider_create()
    try:
        r = await client.post(
            "/providers/test",
            headers=headers,
            json={
                "kind": "deepseek",
                "base_url": "https://api.deepseek.com/v1",
                "models_url": "https://api.deepseek.com/v1/models",
                "api_key": "sk-test",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["model_count"] == 3
        assert body["sample_models"] == ["alpha", "beta", "gamma"]
        assert captured == {"kind": "deepseek", "key": "sk-test"}
        async with factory() as session:
            count = (
                await session.execute(select(func.count()).select_from(Provider))
            ).scalar()
        assert count == 0
    finally:
        await client.aclose()
        await engine.dispose()


async def test_provider_test_reuses_stored_key(monkeypatch):
    captured = {}

    async def fake_list_models(provider):
        captured["key"] = provider.api_key
        return ["m"]

    monkeypatch.setattr("agentbox_api.routers.providers.list_models", fake_list_models)
    engine, factory, client, headers = await _app_with_provider_create()
    try:
        async with factory() as session:
            session.add(
                Provider(
                    id="p1",
                    name="stored",
                    kind="generic",
                    api_key="sk-stored",
                    models_url="https://example.test/models",
                )
            )
            await session.commit()
        r = await client.post(
            "/providers/test",
            headers=headers,
            json={"kind": "generic", "provider_id": "p1", "api_key": ""},
        )
        assert r.json()["ok"] is True
        assert captured["key"] == "sk-stored"
    finally:
        await client.aclose()
        await engine.dispose()


async def test_provider_test_normalizes_failures(monkeypatch):
    engine, factory, client, headers = await _app_with_provider_create()
    try:

        async def unauthorized(_provider):
            raise httpx.HTTPStatusError(
                "unauthorized",
                request=httpx.Request("GET", "https://example.test/models"),
                response=httpx.Response(401),
            )

        monkeypatch.setattr("agentbox_api.routers.providers.list_models", unauthorized)
        r = await client.post(
            "/providers/test",
            headers=headers,
            json={"kind": "generic", "models_url": "https://example.test/models"},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is False
        assert r.json()["error"]["code"] == "unauthorized"

        monkeypatch.setattr(
            "agentbox_api.routers.providers.list_models",
            lambda _provider: (_ for _ in ()).throw(ValueError("no models_url")),
        )
        r = await client.post("/providers/test", headers=headers, json={"kind": "generic"})
        assert r.json()["error"]["code"] == "no_models_url"
    finally:
        await client.aclose()
        await engine.dispose()
