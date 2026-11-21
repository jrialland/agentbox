import pathlib

import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import Permission, Role, RolePermissionLink, User, UserRoleLink


async def _make_app(perms: list[str]):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw")))
        s.add(Role(id="r1", name="admin"))
        for i, perm in enumerate(perms):
            s.add(Permission(id=f"p{i}", name=perm))
            s.add(RolePermissionLink(role_id="r1", permission_id=f"p{i}"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        await s.commit()
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    token = (
        await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    ).json()["access_token"]
    return engine, client, {"Authorization": f"Bearer {token}"}


async def test_project_name_and_path_validation(tmp_path: pathlib.Path, monkeypatch):
    engine, client, headers = await _make_app(["projects:create"])
    try:
        response = await client.post(
            "/projects", json={"name": "   ", "path": str(tmp_path)}, headers=headers
        )
        assert response.status_code == 422

        response = await client.post(
            "/projects", json={"name": "P", "path": str(tmp_path / "missing")}, headers=headers
        )
        assert response.status_code == 422

        file_path = tmp_path / "file.txt"
        file_path.write_text("x", encoding="utf-8")
        response = await client.post(
            "/projects", json={"name": "P", "path": str(file_path)}, headers=headers
        )
        assert response.status_code == 422

        monkeypatch.chdir(tmp_path)
        response = await client.post(
            "/projects", json={"name": " P ", "path": "."}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["name"] == "P"
    finally:
        await client.aclose()
        await engine.dispose()


async def test_extra_roots_must_be_absolute_directories(tmp_path: pathlib.Path):
    engine, client, headers = await _make_app(["projects:create"])
    try:
        response = await client.post(
            "/projects",
            json={"name": "P", "path": str(tmp_path), "extra_roots": ["relative"]},
            headers=headers,
        )
        assert response.status_code == 422

        response = await client.post(
            "/projects",
            json={"name": "P", "path": str(tmp_path), "extra_roots": [str(tmp_path / "missing")]},
            headers=headers,
        )
        assert response.status_code == 422
    finally:
        await client.aclose()
        await engine.dispose()


async def test_blank_resource_names_are_rejected(tmp_path: pathlib.Path):
    engine, client, headers = await _make_app(
        ["providers:create", "agents:create", "roles:manage", "users:manage"]
    )
    try:
        assert (
            await client.post(
                "/providers", json={"name": " ", "kind": "generic"}, headers=headers
            )
        ).status_code == 422
        assert (
            await client.post(
                "/agents", json={"name": " ", "model": "m"}, headers=headers
            )
        ).status_code == 422
        assert (
            await client.post("/roles", json={"name": "   "}, headers=headers)
        ).status_code == 422
        assert (
            await client.post(
                "/users", json={"username": " ", "email": "a@x", "password": "pw"}, headers=headers
            )
        ).status_code == 422
    finally:
        await client.aclose()
        await engine.dispose()


async def test_user_password_preserves_whitespace():
    engine, client, headers = await _make_app(["users:manage"])
    try:
        response = await client.post(
            "/users",
            json={"username": "bob", "email": "b@x", "password": " pw "},
            headers=headers,
        )
        assert response.status_code == 200

        response = await client.post("/auth/login", json={"username": "bob", "password": " pw "})
        assert response.status_code == 200

        response = await client.post("/auth/login", json={"username": "bob", "password": "pw"})
        assert response.status_code == 401

        response = await client.post(
            "/users",
            json={"username": "carol", "email": "c@x", "password": "   "},
            headers=headers,
        )
        assert response.status_code == 422
    finally:
        await client.aclose()
        await engine.dispose()
