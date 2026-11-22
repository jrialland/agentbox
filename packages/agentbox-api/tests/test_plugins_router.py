import json
import pathlib

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
from agentbox_models.tables.core import Project

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"


def _write_plugin(root: pathlib.Path, name: str = "acme-tools") -> None:
    plugin = root / name
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text(
        json.dumps(
            {
                "$schema": PLUGIN_SCHEMA,
                "name": name,
                "version": "1.0.0",
                "description": "Acme tools",
            }
        ),
        encoding="utf-8",
    )
    skill = plugin / "skills" / "review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: review\ndescription: Review\n---\nDo it.\n",
        encoding="utf-8",
    )


async def _client(tmp_path):
    engine, factory = create_engine_and_sessionmaker(
        "sqlite+aiosqlite:///:memory:"
    )
    await init_db(engine)
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    async with factory() as s:
        s.add(
            User(
                id="u1",
                username="admin",
                email="a@x",
                password_hash=hash_password("pw"),
            )
        )
        s.add(
            User(
                id="u2",
                username="reader",
                email="r@x",
                password_hash=hash_password("pw"),
            )
        )
        s.add(Role(id="r1", name="admin"))
        s.add(Role(id="r2", name="reader"))
        for index, name in enumerate(["plugins:read", "plugins:write"]):
            s.add(Permission(id=f"p{index}", name=name))
            s.add(
                RolePermissionLink(
                    role_id="r1", permission_id=f"p{index}"
                )
            )
        s.add(Permission(id="p2", name="plugins:read"))
        s.add(RolePermissionLink(role_id="r2", permission_id="p2"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(UserRoleLink(user_id="u2", role_id="r2"))
        s.add(
            Project(
                id="prj",
                name="p",
                path=str(project),
                owner_id="u1",
            )
        )
        await s.commit()
    app = create_app(
        Settings(
            jwt_secret="s" * 32,
            plugins_user_dir=str(tmp_path / "user"),
            plugins_data_dir=str(tmp_path / "data"),
        ),
        engine=engine,
        session_factory=factory,
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    return engine, client


async def _login(client, username):
    token = (
        await client.post(
            "/auth/login",
            json={"username": username, "password": "pw"},
        )
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_list_enable_and_get_plugin(tmp_path):
    _write_plugin(tmp_path / "user")
    engine, client = await _client(tmp_path)
    try:
        admin = await _login(client, "admin")
        listed = await client.get("/plugins?project_id=prj", headers=admin)
        assert listed.status_code == 200
        plugin = listed.json()[0]
        assert plugin["name"] == "acme-tools"
        assert plugin["scope"] == "global"
        assert plugin["enabled"] is False
        assert plugin["skills"][0]["name"] == "acme-tools:review"

        enabled = await client.put(
            "/plugins/state",
            json={
                "plugin_name": "acme-tools",
                "scope": "global",
                "enabled": True,
            },
            headers=admin,
        )
        assert enabled.status_code == 200
        assert enabled.json()["enabled"] is True

        detail = await client.get(
            "/plugins/global/acme-tools?project_id=prj", headers=admin
        )
        assert detail.status_code == 200
        assert detail.json()["version"] == "1.0.0"
    finally:
        await client.aclose()
        await engine.dispose()


async def test_project_scope_and_write_permission(tmp_path):
    project_plugins = tmp_path / "project" / ".agents" / "plugins"
    project_plugins.mkdir(parents=True)
    _write_plugin(project_plugins)
    engine, client = await _client(tmp_path)
    try:
        admin = await _login(client, "admin")
        listed = await client.get("/plugins?project_id=prj", headers=admin)
        assert any(
            item["scope"] == "project" for item in listed.json()
        )
        missing_project = await client.put(
            "/plugins/state",
            json={
                "plugin_name": "acme-tools",
                "scope": "project",
                "enabled": True,
            },
            headers=admin,
        )
        assert missing_project.status_code == 400

        reader = await _login(client, "reader")
        forbidden = await client.put(
            "/plugins/state",
            json={
                "plugin_name": "acme-tools",
                "scope": "global",
                "enabled": True,
            },
            headers=reader,
        )
        assert forbidden.status_code == 403
    finally:
        await client.aclose()
        await engine.dispose()
