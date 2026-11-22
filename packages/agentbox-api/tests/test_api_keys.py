from datetime import UTC, datetime, timedelta

import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import (
    ApiKey,
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)


async def _setup(perms=("api_keys:manage", "projects:read")):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        await s.flush()
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r1", name="role"))
        for i, p in enumerate(perms):
            s.add(Permission(id=f"p{i}", name=p))
            await s.flush()
            s.add(RolePermissionLink(role_id="r1", permission_id=f"p{i}"))
        await s.flush()
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(User(id="u2", username="bob", email="b@x", password_hash=hash_password("pw")))
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


async def test_create_key_with_subset_scopes_and_use_it():
    engine, client, _ = await _setup()
    try:
        h = await _auth(client)
        r = await client.post(
            "/api-keys", json={"scopes": ["projects:read"]}, headers=h
        )
        assert r.status_code == 200
        body = r.json()
        assert body["key"]
        assert body["scopes"] == ["projects:read"]
        key_h = {"Authorization": f"Bearer {body['key']}"}
        assert (await client.get("/projects", headers=key_h)).status_code == 200
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_keys_has_no_hash_and_is_personal():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        await client.post("/api-keys", json={"scopes": []}, headers=h)
        async with factory() as s:
            await s.flush()
            s.add(ApiKey(id="other", user_id="u2", key_hash="h"))
            await s.commit()
        r = await client.get("/api-keys", headers=h)
        ids = [k["id"] for k in r.json()]
        assert "other" not in ids
        assert all("key_hash" not in k for k in r.json())
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_rejects_scope_not_held():
    engine, client, _ = await _setup()
    try:
        h = await _auth(client)
        r = await client.post(
            "/api-keys", json={"scopes": ["agents:create"]}, headers=h
        )
        assert r.status_code == 400
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_rejects_past_expiry():
    engine, client, _ = await _setup()
    try:
        h = await _auth(client)
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        r = await client.post(
            "/api-keys", json={"scopes": [], "expires_at": past}, headers=h
        )
        assert r.status_code == 400
    finally:
        await client.aclose()
        await engine.dispose()


async def test_revoke_soft_and_blocks_auth():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        raw = (
            await client.post(
                "/api-keys", json={"scopes": ["projects:read"]}, headers=h
            )
        ).json()["key"]
        key_h = {"Authorization": f"Bearer {raw}"}
        kid = (await client.get("/api-keys", headers=h)).json()[0]["id"]
        r = await client.delete(f"/api-keys/{kid}", headers=h)
        assert r.status_code == 200
        async with factory() as s:
            row = await s.get(ApiKey, kid)
        assert row is not None and row.revoked_at is not None
        assert (await client.get("/projects", headers=key_h)).status_code == 401
        listed = (await client.get("/api-keys", headers=h)).json()
        assert any(k["id"] == kid and k["revoked_at"] for k in listed)
    finally:
        await client.aclose()
        await engine.dispose()


async def test_expired_key_is_rejected():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        raw = (
            await client.post(
                "/api-keys", json={"scopes": ["projects:read"]}, headers=h
            )
        ).json()["key"]
        kid = (await client.get("/api-keys", headers=h)).json()[0]["id"]
        async with factory() as s:
            row = await s.get(ApiKey, kid)
            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            s.add(row)
            await s.commit()
        r = await client.get("/projects", headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 401
    finally:
        await client.aclose()
        await engine.dispose()


async def test_cannot_revoke_others_key():
    engine, client, factory = await _setup()
    try:
        h = await _auth(client)
        async with factory() as s:
            await s.flush()
            s.add(ApiKey(id="other", user_id="u2", key_hash="h"))
            await s.commit()
        r = await client.delete("/api-keys/other", headers=h)
        assert r.status_code == 404
    finally:
        await client.aclose()
        await engine.dispose()
