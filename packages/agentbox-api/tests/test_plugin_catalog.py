import json
import pathlib

from agentbox_api.plugin_catalog import PluginCatalog

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"


def _plugin(
    root: pathlib.Path,
    name: str = "acme-tools",
    extra: dict | None = None,
) -> pathlib.Path:
    plugin = root / name
    plugin.mkdir(parents=True)
    manifest = {"$schema": PLUGIN_SCHEMA, "name": name}
    manifest.update(extra or {})
    (plugin / "plugin.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return plugin


def _skill(plugin: pathlib.Path, name: str = "review") -> None:
    skill = plugin / "skills" / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Review code\n---\nDo it.\n",
        encoding="utf-8",
    )


def _mcp(plugin: pathlib.Path, servers: dict) -> None:
    (plugin / "mcp.json").write_text(
        json.dumps({"$schema": MCP_SCHEMA, "mcpServers": servers}),
        encoding="utf-8",
    )


def _catalog(tmp_path: pathlib.Path) -> PluginCatalog:
    return PluginCatalog(
        str(tmp_path / "user"), str(tmp_path / "data")
    )


def test_discovers_valid_skill_and_stdio_server(tmp_path):
    plugin = _plugin(tmp_path / "user")
    _skill(plugin)
    (plugin / "bin").mkdir()
    (plugin / "bin" / "server").write_text("", encoding="utf-8")
    _mcp(
        plugin,
        {
            "local": {
                "type": "stdio",
                "command": "./bin/server",
                "args": ["--data", "${PLUGIN_DATA}"],
                "cwd": "${PLUGIN_ROOT}",
            }
        },
    )

    loaded = _catalog(tmp_path).discover(str(tmp_path / "project"), "p1")[0]
    assert loaded.manifest is not None
    assert loaded.manifest.name == "acme-tools"
    assert loaded.skills[0].scoped_name == "acme-tools:review"
    server = loaded.mcp_servers[0]
    assert server.transport == "stdio"
    assert server.command.endswith("bin\\server") or server.command.endswith(
        "bin/server"
    )
    assert str(tmp_path / "data" / "acme-tools") in server.args[1]
    assert server.cwd == str(plugin.resolve())
    assert not [i for i in loaded.issues if i.severity == "fatal"]


def test_unknown_manifest_field_warns_but_loads(tmp_path):
    _plugin(tmp_path / "user", extra={"unknown": True})
    loaded = _catalog(tmp_path).discover(str(tmp_path / "project"), "p1")[0]
    assert loaded.manifest is not None
    assert any(issue.severity == "warning" for issue in loaded.issues)


def test_non_object_extensions_warns_but_loads(tmp_path):
    _plugin(tmp_path / "user", extra={"extensions": "nope"})
    loaded = _catalog(tmp_path).discover(str(tmp_path / "project"), "p1")[0]
    assert loaded.manifest is not None
    assert any(
        issue.component == "manifest" and issue.severity == "warning"
        for issue in loaded.issues
    )


def test_missing_or_unsupported_schema_is_fatal(tmp_path):
    plugin = _plugin(tmp_path / "user")
    (plugin / "plugin.json").write_text(
        json.dumps({"name": "acme-tools"}), encoding="utf-8"
    )
    loaded = _catalog(tmp_path).discover(str(tmp_path / "project"), "p1")[0]
    assert loaded.manifest is None
    assert any(issue.severity == "fatal" for issue in loaded.issues)


def test_invalid_name_rejects_plugin(tmp_path):
    _plugin(tmp_path / "user", name="Bad_Name")
    loaded = _catalog(tmp_path).discover(str(tmp_path / "project"), "p1")[0]
    assert loaded.manifest is None
    assert any(issue.severity == "fatal" for issue in loaded.issues)


def test_invalid_skill_is_skipped(tmp_path):
    plugin = _plugin(tmp_path / "user")
    skill = plugin / "skills" / "broken"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("not frontmatter", encoding="utf-8")
    loaded = _catalog(tmp_path).discover(str(tmp_path / "project"), "p1")[0]
    assert loaded.manifest is not None
    assert loaded.skills == ()
    assert any(
        issue.component.startswith("skill:") for issue in loaded.issues
    )


def test_invalid_top_level_mcp_keeps_skills(tmp_path):
    plugin = _plugin(tmp_path / "user")
    _skill(plugin)
    (plugin / "mcp.json").write_text(
        json.dumps({"$schema": MCP_SCHEMA}), encoding="utf-8"
    )
    loaded = _catalog(tmp_path).discover(str(tmp_path / "project"), "p1")[0]
    assert loaded.manifest is not None
    assert loaded.skills
    assert loaded.mcp_servers == ()
    assert any(issue.component == "mcp" for issue in loaded.issues)


def test_invalid_server_entry_is_skipped(tmp_path):
    plugin = _plugin(tmp_path / "user")
    _skill(plugin)
    (plugin / "bin").mkdir()
    (plugin / "bin" / "server").write_text("", encoding="utf-8")
    _mcp(
        plugin,
        {
            "bad": {"type": "stdio", "command": "./bin/server", "extra": 1},
            "good": {"type": "stdio", "command": "./bin/server"},
        },
    )
    loaded = _catalog(tmp_path).discover(str(tmp_path / "project"), "p1")[0]
    assert loaded.skills
    assert [server.name for server in loaded.mcp_servers] == ["good"]
    assert any(issue.component == "mcp:bad" for issue in loaded.issues)


def test_path_escape_command_is_skipped(tmp_path):
    plugin = _plugin(tmp_path / "user")
    _mcp(
        plugin,
        {"bad": {"type": "stdio", "command": "../server"}},
    )
    loaded = _catalog(tmp_path).discover(str(tmp_path / "project"), "p1")[0]
    assert loaded.manifest is not None
    assert loaded.mcp_servers == ()
    assert any(issue.component == "mcp:bad" for issue in loaded.issues)


def test_remote_url_and_headers(tmp_path):
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
    loaded = _catalog(tmp_path).discover(str(tmp_path / "project"), "p1")[0]
    server = loaded.mcp_servers[0]
    assert server.transport == "streamable-http"
    assert server.url == "https://example.test/mcp"
    assert server.headers == {"X-Tenant": "public"}


def test_remote_http_non_loopback_is_rejected(tmp_path):
    plugin = _plugin(tmp_path / "user")
    _mcp(
        plugin,
        {
            "remote": {
                "type": "streamable-http",
                "url": "http://example.test/mcp",
            }
        },
    )
    loaded = _catalog(tmp_path).discover(str(tmp_path / "project"), "p1")[0]
    assert loaded.mcp_servers == ()
    assert any(issue.component == "mcp:remote" for issue in loaded.issues)


def test_duplicate_header_name_is_rejected(tmp_path):
    plugin = _plugin(tmp_path / "user")
    _mcp(
        plugin,
        {
            "remote": {
                "type": "sse",
                "url": "https://example.test/sse",
                "headers": {"X-Test": "a", "x-test": "b"},
            }
        },
    )
    loaded = _catalog(tmp_path).discover(str(tmp_path / "project"), "p1")[0]
    assert loaded.mcp_servers == ()
    assert any(issue.component == "mcp:remote" for issue in loaded.issues)


def test_global_and_project_plugins_are_both_returned(tmp_path):
    _plugin(tmp_path / "user")
    project_plugins = tmp_path / "project" / ".agents" / "plugins"
    project_plugins.mkdir(parents=True)
    _plugin(project_plugins)

    plugins = _catalog(tmp_path).discover(str(tmp_path / "project"), "p1")
    scopes = [plugin.scope for plugin in plugins]
    assert scopes == ["global", "project"]
