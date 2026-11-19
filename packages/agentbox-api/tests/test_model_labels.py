import httpx
from sqlmodel import select

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
from agentbox_models.tables.core import Model, ModelLabelLink, Provider


async def _setup():
    perms = (
        "providers:create",
        "providers:read",
        "providers:delete",
        "agents:create",
        "agents:read",
    )
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
        for i, permission in enumerate(perms):
            s.add(Permission(id=f"p{i}", name=permission))
            s.add(RolePermissionLink(role_id="r1", permission_id=f"p{i}"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(Provider(id="prov", name="prov", kind="test"))
        s.add(Model(id="m1", provider_id="prov", name="alpha"))
        s.add(Model(id="m2", provider_id="prov", name="beta"))
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


async def test_assign_labels_case_folded_and_listed():
    engine, client, _ = await _setup()
    try:
        h = await _auth(client)
        r = await client.put(
            "/models/m1/labels",
            json={
                "labels": [
                    {"label": " Fast ", "priority": 5},
                    {"label": "fast", "priority": 2},
                ]
            },
            headers=h,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "alpha"
        assert body["labels"] == [
            {"id": body["labels"][0]["id"], "name": "fast", "priority": 2}
        ]

        r = await client.get("/labels", headers=h)
        assert r.status_code == 200
        assert [label["name"] for label in r.json()] == ["fast"]

        r = await client.get("/models", headers=h)
        alpha = next(m for m in r.json() if m["id"] == "m1")
        assert [label["name"] for label in alpha["labels"]] == ["fast"]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_model_with_labels():
    engine, client, _ = await _setup()
    try:
        h = await _auth(client)
        r = await client.post(
            "/models",
            json={
                "provider_id": "prov",
                "name": "gamma",
                "labels": [{"label": "cheap", "priority": 1}],
            },
            headers=h,
        )
        assert r.status_code == 200
        assert [label["name"] for label in r.json()["labels"]] == ["cheap"]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_delete_model_and_provider_remove_links():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        await client.put(
            "/models/m1/labels", json={"labels": [{"label": "fast"}]}, headers=h
        )
        assert (await client.delete("/models/m1", headers=h)).status_code == 200
        async with factory() as s:
            links = (await s.execute(select(ModelLabelLink))).scalars().all()
            assert links == []

        await client.put(
            "/models/m2/labels", json={"labels": [{"label": "fast"}]}, headers=h
        )
        assert (await client.delete("/providers/prov", headers=h)).status_code == 200
        async with factory() as s:
            assert (await s.execute(select(ModelLabelLink))).scalars().all() == []
    finally:
        await client.aclose()
        await engine.dispose()
