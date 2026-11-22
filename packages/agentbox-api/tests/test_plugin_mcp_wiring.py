import json
import pathlib

from agentbox_api.plugin_service import PluginService
from agentbox_api.security import hash_password
from agentbox_api.skills import prepare_agent
from agentbox_harness.spec import (
    AgentSpec,
    McpToolBinding,
    ModelBinding,
    PluginMcpBinding,
)
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.repos.agents import AgentRepository
from agentbox_models.tables.auth import User
from agentbox_models.tables.core import Model, Project, Provider

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"


def _write_plugin(root: pathlib.Path) -> pathlib.Path:
    plugin = root / "acme-tools"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text(
        json.dumps({"$schema": PLUGIN_SCHEMA, "name": "acme-tools"}),
        encoding="utf-8",
    )
    (plugin / "bin").mkdir()
    (plugin / "bin" / "server").write_text("", encoding="utf-8")
    (plugin / "mcp.json").write_text(
        json.dumps(
            {
                "$schema": MCP_SCHEMA,
                "mcpServers": {
                    "local": {
                        "type": "stdio",
                        "command": "./bin/server",
                        "env": {"EXTRA": "${PLUGIN_ROOT}"},
                        "cwd": "${PLUGIN_ROOT}",
                    }
                },
            }
        ),
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
    project2 = tmp_path / "project2"
    project2.mkdir()
    async with factory() as s:
        s.add(
            User(
                id="u1",
                username="alice",
                email="a@x",
                password_hash=hash_password("pw"),
            )
        )
        s.add(Provider(id="prov", name="test", kind="test"))
        await s.flush()
        s.add(Model(id="m", provider_id="prov", name="test-model"))
        await s.flush()
        s.add(
            Project(
                id="prj",
                name="p",
                path=str(project),
                owner_id="u1",
            )
        )
        s.add(
            Project(
                id="prj2",
                name="p2",
                path=str(project2),
                owner_id="u1",
            )
        )
        await s.commit()
    return engine, factory, project


def _spec(binding: PluginMcpBinding) -> AgentSpec:
    return AgentSpec(
        name="bot",
        description="d",
        instructions="i",
        tool_bindings=[],
        plugin_mcp_bindings=[binding],
        model_binding=ModelBinding(model="test-model", provider="test"),
    )


async def test_prepare_agent_resolves_global_plugin_mcp(tmp_path):
    engine, factory, project = await _setup(tmp_path)
    plugin = _write_plugin(tmp_path / "user")
    try:
        service = PluginService(
            factory, str(tmp_path / "user"), str(tmp_path / "data")
        )
        await service.set_enabled(
            "acme-tools", "global", None, True, str(project)
        )
        await AgentRepository(factory).save(
            _spec(PluginMcpBinding(plugin="acme-tools", server="local"))
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
        binding = next(
            item
            for item in prepared.spec.tool_bindings
            if isinstance(item, McpToolBinding)
            and item.id == "acme-tools:local"
        )
        assert binding.command.endswith("server")
        assert binding.env["PLUGIN_ROOT"] == str(plugin.resolve())
        assert binding.env["PLUGIN_DATA"] == str(
            (tmp_path / "data" / "acme-tools").resolve()
        )
        assert plugin.resolve() in prepared.plugin_roots
    finally:
        await engine.dispose()


async def test_mismatched_project_binding_is_skipped(tmp_path):
    engine, factory, project = await _setup(tmp_path)
    _write_plugin(tmp_path / "user")
    try:
        service = PluginService(
            factory, str(tmp_path / "user"), str(tmp_path / "data")
        )
        await service.set_enabled(
            "acme-tools", "global", None, True, str(project)
        )
        await AgentRepository(factory).save(
            _spec(
                PluginMcpBinding(
                    plugin="acme-tools",
                    server="local",
                    project_id="prj2",
                )
            )
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
        assert not [
            item
            for item in prepared.spec.tool_bindings
            if isinstance(item, McpToolBinding)
            and item.id == "acme-tools:local"
        ]
    finally:
        await engine.dispose()
