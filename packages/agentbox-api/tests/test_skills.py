import pathlib

from agentbox_api.skills import augment_spec, discover_skills, make_activate_tool
from agentbox_harness.spec import AgentSpec, ModelBinding, NativeToolBinding


def _write_skill(dir_: pathlib.Path, name: str, desc: str, body: str) -> None:
    d = dir_ / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n{body}\n", encoding="utf-8"
    )


def test_discovery_precedence(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    pdir = project / ".agents" / "skills"
    pdir.mkdir(parents=True)
    user = tmp_path / "user"
    user.mkdir()
    _write_skill(pdir, "shared", "project version", "project body")
    _write_skill(user, "shared", "user version", "user body")
    _write_skill(user, "only-user", "user only", "u body")

    skills = discover_skills(str(project), str(user))
    by = {s.name: s for s in skills}
    assert by["shared"].scope == "project"
    assert by["shared"].description == "project version"
    assert by["only-user"].scope == "user"
    assert "commit-message" in by and by["commit-message"].scope == "builtin"


def test_augment_and_activate(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _write_skill(project / ".agents" / "skills", "demo", "d", "# Demo\nDo it.")
    skills = discover_skills(str(project), str(tmp_path / "missing"))

    spec = AgentSpec(
        name="a",
        description="",
        instructions="base",
        tool_bindings=[],
        model_binding=ModelBinding(model="test", provider="test"),
    )
    augmented = augment_spec(spec, skills)
    assert "available_skills" in augmented.instructions
    assert any(
        isinstance(b, NativeToolBinding) and b.name == "activate_skill"
        for b in augmented.tool_bindings
    )

    import asyncio

    tool = make_activate_tool(skills)
    out = asyncio.run(tool("demo"))
    assert "Do it." in out and "Skill directory" in out


async def test_explicit_skill_activation(tmp_path):
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
    from agentbox_models.tables.core import (
        Agent,
        Model,
        Project,
        Provider,
        SessionRow,
    )

    skill_dir = tmp_path / ".agents" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: d\n---\n# Demo\nbody", encoding="utf-8"
    )

    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r1", name="role"))
        s.add(Permission(id="p0", name="sessions:create"))
        s.add(RolePermissionLink(role_id="r1", permission_id="p0"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(Provider(id="prov", name="test", kind="test"))
        s.add(Model(id="m", provider_id="prov", name="test-model"))
        s.add(
            Agent(
                id="ag",
                name="bot",
                description="d",
                instructions="i",
                model_id="m",
                mode_definitions='[{"name":"agent","flags":{"write":true}}]',
            )
        )
        s.add(Project(id="prj", name="p", path=str(tmp_path), owner_id="u1"))
        s.add(SessionRow(id="s1", project_id="prj", agent_id="ag"))
        await s.commit()
    app = create_app(
        Settings(jwt_secret="s" * 32, skills_user_dir=str(tmp_path / "userskills")),
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
        h = {"Authorization": f"Bearer {token}"}
        ok = await client.post(
            "/sessions/s1/messages", json={"content": "hi", "skill": "demo"}, headers=h
        )
        assert ok.status_code == 200
        bad = await client.post(
            "/sessions/s1/messages", json={"content": "hi", "skill": "nope"}, headers=h
        )
        assert bad.status_code == 400
    finally:
        await client.aclose()
        await engine.dispose()
