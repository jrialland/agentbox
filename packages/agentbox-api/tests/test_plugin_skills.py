import json
import pathlib

import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.plugin_service import PluginService
from agentbox_api.security import hash_password
from agentbox_api.skills import make_activate_tool, prepare_agent
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import (
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)
from agentbox_models.tables.core import Agent, Model, Project, Provider

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"


def _write_plugin(root: pathlib.Path, name: str = "acme-tools") -> pathlib.Path:
    plugin = root / name
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text(
        json.dumps({"$schema": PLUGIN_SCHEMA, "name": name}),
        encoding="utf-8",
    )
    skill = plugin / "skills" / "review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: review\ndescription: Review code\n---\nDo it.\n",
        encoding="utf-8",
    )
    return plugin


async def _setup(tmp_path):
    engine, factory = create_engine_and_sessionmaker(
        "sqlite+aiosqlite:///:memory:"
    )
    await init_db(engine)
    project = tmp_path / "project"
    project.mkdir()
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
        for index, name in enumerate(["agents:create", "agents:read"]):
            s.add(Permission(id=f"p{index}", name=name))
            s.add(
                RolePermissionLink(
                    role_id="r1", permission_id=f"p{index}"
                )
            )
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(Provider(id="prov", name="test", kind="test"))
        await s.flush()
        s.add(Model(id="m", provider_id="prov", name="test-model"))
        await s.flush()
        s.add(
            Agent(
                id="ag",
                name="bot",
                description="d",
                instructions="i",
                model_id="m",
            )
        )
        await s.flush()
        s.add(
            Project(
                id="prj",
                name="p",
                path=str(project),
                owner_id="u1",
            )
        )
        await s.commit()
    return engine, factory, project


async def test_prepare_agent_exposes_namespaced_plugin_skill(tmp_path):
    engine, factory, project = await _setup(tmp_path)
    plugin = _write_plugin(tmp_path / "user")
    try:
        service = PluginService(
            factory, str(tmp_path / "user"), str(tmp_path / "data")
        )
        await service.set_enabled(
            "acme-tools", "global", None, True, str(project)
        )
        prepared = await prepare_agent(
            factory,
            "bot",
            str(project),
            str(tmp_path / "skills"),
            session_id="s1",
            project_id="prj",
            plugins_user_dir=str(tmp_path / "user"),
            plugins_data_dir=str(tmp_path / "data"),
        )
        skill = next(
            item for item in prepared.skills if item.name == "acme-tools:review"
        )
        assert skill.scope == "plugin"
        assert skill.plugin == "acme-tools"
        assert plugin.resolve() in prepared.plugin_roots
        assert "acme-tools:review" in prepared.spec.instructions
        text = await make_activate_tool(prepared.skills)("acme-tools:review")
        assert "Do it." in text
    finally:
        await engine.dispose()


async def test_skills_api_rejects_plugin_edits(tmp_path):
    engine, factory, project = await _setup(tmp_path)
    _write_plugin(tmp_path / "user")
    service = PluginService(
        factory, str(tmp_path / "user"), str(tmp_path / "data")
    )
    await service.set_enabled(
        "acme-tools", "global", None, True, str(project)
    )
    app = create_app(
        Settings(
            jwt_secret="s" * 32,
            skills_user_dir=str(tmp_path / "userskills"),
            plugins_user_dir=str(tmp_path / "user"),
            plugins_data_dir=str(tmp_path / "data"),
        ),
        engine=engine,
        session_factory=factory,
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    try:
        token = (
            await client.post(
                "/auth/login", json={"username": "alice", "password": "pw"}
            )
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        listed = await client.get("/skills?project_id=prj", headers=headers)
        assert listed.status_code == 200
        assert any(
            item["name"] == "acme-tools:review"
            and item["scope"] == "plugin"
            for item in listed.json()
        )
        put = await client.put(
            "/skills/acme-tools:review",
            json={"description": "x", "body": "x"},
            headers=headers,
        )
        assert put.status_code == 400
        delete = await client.delete(
            "/skills/acme-tools:review", headers=headers
        )
        assert delete.status_code == 400
    finally:
        await client.aclose()
        await engine.dispose()
