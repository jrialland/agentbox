import json
import pathlib

from agentbox_api.plugin_service import PluginService
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import User
from agentbox_models.tables.core import PluginState, Project

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"


def _plugin(
    root: pathlib.Path,
    name: str = "acme-tools",
    skill: str = "review",
) -> pathlib.Path:
    plugin = root / name
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text(
        json.dumps({"$schema": PLUGIN_SCHEMA, "name": name}),
        encoding="utf-8",
    )
    skill_dir = plugin / "skills" / skill
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {skill}\ndescription: {skill} skill\n---\nDo it.\n",
        encoding="utf-8",
    )
    return plugin


def _mcp(plugin: pathlib.Path, servers: dict) -> None:
    (plugin / "mcp.json").write_text(
        json.dumps({"$schema": MCP_SCHEMA, "mcpServers": servers}),
        encoding="utf-8",
    )


async def _setup(tmp_path):
    engine, factory = create_engine_and_sessionmaker(
        "sqlite+aiosqlite:///:memory:"
    )
    await init_db(engine)
    project = tmp_path / "project"
    project.mkdir()
    project2 = tmp_path / "project2"
    project2.mkdir()
    async with factory() as s:
        s.add(
            User(
                id="u1",
                username="u",
                email="u@example.com",
                password_hash="x",
                is_active=True,
            )
        )
        s.add(
            Project(
                id="p1",
                name="p1",
                path=str(project),
                owner_id="u1",
            )
        )
        s.add(
            Project(
                id="p2",
                name="p2",
                path=str(project2),
                owner_id="u1",
            )
        )
        await s.commit()
    service = PluginService(
        factory, str(tmp_path / "user"), str(tmp_path / "data")
    )
    return engine, factory, service, project, project2


async def test_enable_global_plugin_and_list_skills(tmp_path):
    engine, _factory, service, project, _project2 = await _setup(tmp_path)
    plugin = _plugin(tmp_path / "user")
    try:
        await service.set_enabled(
            "acme-tools", "global", None, True, str(project)
        )
        skills = await service.list_plugin_skills(None, str(project))
        assert [skill.scoped_name for skill in skills] == [
            "acme-tools:review"
        ]
        assert await service.plugin_roots(None, str(project)) == [
            plugin.resolve()
        ]
    finally:
        await engine.dispose()


async def test_project_plugin_is_scoped(tmp_path):
    engine, _factory, service, project, project2 = await _setup(tmp_path)
    project_plugins = project / ".agents" / "plugins"
    project_plugins.mkdir(parents=True)
    _plugin(project_plugins, skill="project-skill")
    try:
        await service.set_enabled(
            "acme-tools", "project", "p1", True, str(project)
        )
        assert [
            skill.scoped_name
            for skill in await service.list_plugin_skills("p1", str(project))
        ] == ["acme-tools:project-skill"]
        assert (
            await service.list_plugin_skills("p2", str(project2))
        ) == []
    finally:
        await engine.dispose()


async def test_project_plugin_shadows_global_only_when_enabled(tmp_path):
    engine, _factory, service, project, _project2 = await _setup(tmp_path)
    _plugin(tmp_path / "user", skill="global-skill")
    project_plugins = project / ".agents" / "plugins"
    project_plugins.mkdir(parents=True)
    _plugin(project_plugins, skill="project-skill")
    try:
        await service.set_enabled(
            "acme-tools", "global", None, True, str(project)
        )
        assert [
            skill.scoped_name
            for skill in await service.list_plugin_skills(None, str(project))
        ] == ["acme-tools:global-skill"]

        await service.set_enabled(
            "acme-tools", "project", "p1", True, str(project)
        )
        assert [
            skill.scoped_name
            for skill in await service.list_plugin_skills("p1", str(project))
        ] == ["acme-tools:project-skill"]

        views = await service.list_plugins("p1", str(project))
        global_view = next(
            view for view in views if view.scope == "global"
        )
        assert global_view.shadowed is True
        assert global_view.enabled is False

        await service.set_enabled(
            "acme-tools", "project", "p1", False, str(project)
        )
        assert [
            skill.scoped_name
            for skill in await service.list_plugin_skills("p1", str(project))
        ] == ["acme-tools:global-skill"]
    finally:
        await engine.dispose()


async def test_stale_state_is_ignored(tmp_path):
    engine, factory, service, project, _project2 = await _setup(tmp_path)
    async with factory() as s:
        s.add(
            PluginState(
                id="global:missing",
                plugin_name="missing",
                scope="global",
                enabled=True,
            )
        )
        await s.commit()
    try:
        assert await service.list_plugins(None, str(project)) == []
        assert await service.enabled_plugins(None, str(project)) == []
    finally:
        await engine.dispose()


async def test_resolve_stdio_mcp_expands_plugin_variables(tmp_path):
    engine, _factory, service, project, _project2 = await _setup(tmp_path)
    plugin = _plugin(tmp_path / "user")
    (plugin / "bin").mkdir()
    (plugin / "bin" / "server").write_text("", encoding="utf-8")
    _mcp(
        plugin,
        {
            "local": {
                "type": "stdio",
                "command": "./bin/server",
                "args": ["--data", "${PLUGIN_DATA}/cache"],
                "env": {"EXTRA": "${PLUGIN_ROOT}"},
                "cwd": "${PLUGIN_ROOT}",
            }
        },
    )
    try:
        await service.set_enabled(
            "acme-tools", "global", None, True, str(project)
        )
        resolved = await service.resolve_mcp(
            "acme-tools", "local", None, str(project)
        )
        assert resolved is not None
        assert resolved.id == "acme-tools:local"
        assert resolved.command.endswith("server")
        assert "acme-tools" in resolved.args[1]
        assert resolved.args[1].endswith("cache")
        assert resolved.env["PLUGIN_ROOT"] == str(plugin.resolve())
        assert resolved.env["PLUGIN_DATA"] == str(
            (tmp_path / "data" / "acme-tools").resolve()
        )
        assert resolved.cwd == str(plugin.resolve())
        assert (tmp_path / "data" / "acme-tools").is_dir()
    finally:
        await engine.dispose()


async def test_resolve_remote_mcp_headers(tmp_path):
    engine, _factory, service, project, _project2 = await _setup(tmp_path)
    plugin = _plugin(tmp_path / "user")
    _mcp(
        plugin,
        {
            "remote": {
                "type": "streamable-http",
                "url": "https://example.test/mcp",
                "headers": {"X-Tenant": "public"},
            }
        },
    )
    try:
        await service.set_enabled(
            "acme-tools", "global", None, True, str(project)
        )
        resolved = await service.resolve_mcp(
            "acme-tools", "remote", None, str(project)
        )
        assert resolved is not None
        assert resolved.transport == "streamable-http"
        assert resolved.url == "https://example.test/mcp"
        assert resolved.headers == {"X-Tenant": "public"}
    finally:
        await engine.dispose()
