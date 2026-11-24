"""Discover and load agent plugins from global and project directories.

A plugin contributes a validated ``plugin.json`` manifest plus optional
``skills``, ``mcp.json`` servers, and ``hooks.json`` hooks. Loaders are read-only
and treat plugin content as untrusted: paths are confined to the plugin root,
unknown manifest fields are ignored with warnings, and component failures are
collected as issues instead of aborting discovery.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Literal

from jsonschema import Draft202012Validator
from skills_ref import read_properties, validate

from agentbox_api.plugin_hook_config import PluginHook, load_plugin_hooks
from agentbox_api.plugin_validation import (
    RESERVED_ENV,
    ensure_inside,
    expand,
    resolve_cwd,
    validate_headers,
    validate_url,
)

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"

PluginScope = Literal["global", "project"]
IssueSeverity = Literal["fatal", "warning"]

_KNOWN_MANIFEST_FIELDS = {
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "extensions",
}
_RESERVED_ENV = RESERVED_ENV


def _schema_path(name: str) -> pathlib.Path:
    return (
        pathlib.Path(__file__).parent
        / "schemas"
        / "agent_plugins"
        / "1.0.0"
        / name
    )


def _load_schema(name: str) -> dict[str, Any]:
    return json.loads(_schema_path(name).read_text(encoding="utf-8"))


_MCP_SCHEMA_DOC = _load_schema("mcp.schema.json")
_PLUGIN_VALIDATOR = Draft202012Validator(_load_schema("plugin.schema.json"))
_MCP_TOP_VALIDATOR = Draft202012Validator(
    {
        "type": "object",
        "properties": {
            "$schema": {"const": MCP_SCHEMA},
            "mcpServers": {"type": "object"},
        },
        "required": ["$schema", "mcpServers"],
        "additionalProperties": False,
    }
)
_MCP_SERVER_VALIDATOR = Draft202012Validator(
    {"$ref": "#/$defs/server", "$defs": _MCP_SCHEMA_DOC["$defs"]}
)


@dataclass(frozen=True)
class PluginIssue:
    """A problem encountered while loading a plugin component."""

    severity: IssueSeverity
    component: str
    message: str


@dataclass(frozen=True)
class PluginManifest:
    """Validated metadata from a plugin's ``plugin.json``."""

    schema: str
    name: str
    root: pathlib.Path
    version: str = ""
    description: str = ""
    author: dict[str, Any] = field(default_factory=dict)
    homepage: str = ""
    repository: str = ""
    license: str = ""
    keywords: tuple[str, ...] = ()
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginSkill:
    """A validated skill shipped inside a plugin."""

    name: str
    description: str
    location: pathlib.Path
    plugin_name: str

    @property
    def scoped_name(self) -> str:
        """Return the ``plugin:skill`` name used to avoid collisions."""
        return f"{self.plugin_name}:{self.name}"


@dataclass(frozen=True)
class PluginMcpServer:
    """A normalized MCP server declaration from ``mcp.json``."""

    name: str
    transport: str
    command: str = ""
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    cwd: str = ""
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LoadedPlugin:
    """A discovered plugin with its parsed components and issues.

    ``manifest`` is ``None`` when the manifest was missing or invalid; other
    components may still carry issues while remaining usable.
    """

    manifest: PluginManifest | None
    root: pathlib.Path
    scope: PluginScope
    project_id: str | None
    skills: tuple[PluginSkill, ...] = ()
    mcp_servers: tuple[PluginMcpServer, ...] = ()
    hooks: tuple[PluginHook, ...] = ()
    issues: tuple[PluginIssue, ...] = ()


def _ensure_inside(root: pathlib.Path, target: pathlib.Path) -> pathlib.Path:
    return ensure_inside(root, target)


def _load_manifest(
    root: pathlib.Path, issues: list[PluginIssue]
) -> PluginManifest | None:
    path = root / "plugin.json"
    try:
        # The manifest path is untrusted; confine it to the plugin root.
        _ensure_inside(root, path)
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        issues.append(
            PluginIssue("fatal", "manifest", "plugin.json escapes plugin root")
        )
        return None
    except Exception as exc:
        issues.append(PluginIssue("fatal", "manifest", f"invalid plugin.json: {exc}"))
        return None
    if not isinstance(raw, dict):
        issues.append(PluginIssue("fatal", "manifest", "plugin.json must be an object"))
        return None
    if raw.get("$schema") != PLUGIN_SCHEMA:
        issues.append(
            PluginIssue("fatal", "manifest", "unsupported or missing $schema")
        )
        return None

    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        # Unknown fields are dropped rather than failing the plugin, so newer
        # manifests remain loadable on older servers.
        if key not in _KNOWN_MANIFEST_FIELDS:
            issues.append(
                PluginIssue("warning", "manifest", f"unknown field {key!r}")
            )
            continue
        normalized[key] = value

    if "extensions" in normalized and not isinstance(
        normalized["extensions"], dict
    ):
        issues.append(
            PluginIssue("warning", "manifest", "extensions must be an object")
        )
        normalized.pop("extensions", None)

    errors = sorted(_PLUGIN_VALIDATOR.iter_errors(normalized), key=str)
    if errors:
        issues.append(PluginIssue("fatal", "manifest", errors[0].message))
        return None

    return PluginManifest(
        schema=normalized["$schema"],
        name=normalized["name"],
        root=root,
        version=normalized.get("version", ""),
        description=normalized.get("description", ""),
        author=normalized.get("author", {}),
        homepage=normalized.get("homepage", ""),
        repository=normalized.get("repository", ""),
        license=normalized.get("license", ""),
        keywords=tuple(normalized.get("keywords", ())),
        extensions=normalized.get("extensions", {}),
    )


def _load_skills(
    root: pathlib.Path, plugin_name: str, issues: list[PluginIssue]
) -> tuple[PluginSkill, ...]:
    skills_dir = root / "skills"
    if not skills_dir.exists():
        return ()
    if not skills_dir.is_dir():
        issues.append(PluginIssue("warning", "skills", "skills is not a directory"))
        return ()
    try:
        _ensure_inside(root, skills_dir)
    except ValueError:
        issues.append(
            PluginIssue("warning", "skills", "skills escapes plugin root")
        )
        return ()

    result: dict[str, PluginSkill] = {}
    for entry in sorted(skills_dir.iterdir(), key=lambda item: item.name):
        skill_md = entry / "SKILL.md"
        if not entry.is_dir() or not skill_md.is_file():
            continue
        try:
            # Confirm the SKILL.md itself stays inside the plugin before
            # handing the directory to the skills validator.
            _ensure_inside(root, skill_md)
            errors = validate(entry)
        except Exception as exc:
            issues.append(
                PluginIssue("warning", f"skill:{entry.name}", str(exc))
            )
            continue
        if errors:
            issues.append(
                PluginIssue(
                    "warning",
                    f"skill:{entry.name}",
                    "; ".join(str(error) for error in errors),
                )
            )
            continue
        try:
            properties = read_properties(entry)
        except Exception as exc:
            issues.append(
                PluginIssue("warning", f"skill:{entry.name}", str(exc))
            )
            continue
        if properties.name in result:
            issues.append(
                PluginIssue(
                    "warning",
                    f"skill:{properties.name}",
                    "duplicate skill name",
                )
            )
            continue
        result[properties.name] = PluginSkill(
            name=properties.name,
            description=properties.description or "",
            location=skill_md,
            plugin_name=plugin_name,
        )
    return tuple(result.values())


def _expand(value: str, root: pathlib.Path, data_root: pathlib.Path) -> str:
    return expand(value, root, data_root)


def _resolve_cwd(
    value: str, root: pathlib.Path, data_root: pathlib.Path
) -> str:
    return resolve_cwd(value, root, data_root)


def _validate_url(url: str) -> None:
    validate_url(url)


def _validate_headers(headers: dict[str, Any]) -> dict[str, str]:
    return validate_headers(headers)


def _build_mcp_server(
    name: str,
    entry: dict[str, Any],
    root: pathlib.Path,
    data_root: pathlib.Path,
) -> PluginMcpServer:
    transport = entry["type"]
    if transport == "stdio":
        command = entry["command"]
        # Only bare executables or plugin-relative ``./`` commands are allowed,
        # keeping spawned processes tied to the plugin.
        if command.startswith("./"):
            command = str(_ensure_inside(root, root / command[2:]))
        elif "/" in command or "\\" in command:
            raise ValueError(
                "stdio command must be a bare executable or start with ./"
            )
        args = tuple(
            _expand(value, root, data_root) for value in entry.get("args", ())
        )
        env: dict[str, str] = {}
        for key, value in entry.get("env", {}).items():
            if key in _RESERVED_ENV:
                # Runtime-provided variables must not be spoofed by plugins.
                raise ValueError(f"reserved environment variable: {key}")
            env[key] = _expand(value, root, data_root)
        cwd = _resolve_cwd(entry.get("cwd", ""), root, data_root)
        return PluginMcpServer(
            name=name,
            transport="stdio",
            command=command,
            args=args,
            env=env,
            cwd=cwd,
        )
    if transport in {"streamable-http", "sse"}:
        url = entry["url"]
        _validate_url(url)
        headers = _validate_headers(entry.get("headers", {}))
        return PluginMcpServer(
            name=name,
            transport=transport,
            url=url,
            headers=headers,
        )
    raise ValueError(f"unsupported transport: {transport}")


def _load_mcp(
    root: pathlib.Path,
    data_root: pathlib.Path,
    issues: list[PluginIssue],
) -> tuple[PluginMcpServer, ...]:
    path = root / "mcp.json"
    if not path.exists():
        return ()
    if not path.is_file():
        issues.append(PluginIssue("warning", "mcp", "mcp.json is not a file"))
        return ()
    try:
        # mcp.json is untrusted; confine it to the plugin root.
        _ensure_inside(root, path)
    except ValueError:
        issues.append(
            PluginIssue("warning", "mcp", "mcp.json escapes plugin root")
        )
        return ()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        issues.append(PluginIssue("warning", "mcp", f"invalid mcp.json: {exc}"))
        return ()
    errors = sorted(_MCP_TOP_VALIDATOR.iter_errors(raw), key=str)
    if errors:
        issues.append(PluginIssue("warning", "mcp", errors[0].message))
        return ()

    servers: list[PluginMcpServer] = []
    for name, entry in sorted(raw["mcpServers"].items()):
        entry_errors = sorted(_MCP_SERVER_VALIDATOR.iter_errors(entry), key=str)
        if entry_errors:
            issues.append(
                PluginIssue("warning", f"mcp:{name}", entry_errors[0].message)
            )
            continue
        try:
            servers.append(_build_mcp_server(name, entry, root, data_root))
        except ValueError as exc:
            issues.append(PluginIssue("warning", f"mcp:{name}", str(exc)))
    return tuple(servers)


class PluginCatalog:
    """Load plugins from a user-global directory and a project directory.

    The catalog only reads and validates plugin content; enablement state lives
    in :class:`~agentbox_api.plugin_service.PluginService`.
    """

    def __init__(self, user_dir: str, data_dir: str):
        self.user_dir = pathlib.Path(user_dir).expanduser()
        self.data_dir = pathlib.Path(data_dir).expanduser()

    def discover(
        self, project_root: str, project_id: str | None
    ) -> list[LoadedPlugin]:
        """Discover global and project plugins for a project.

        Global plugins are listed first, then project plugins; the service layer
        resolves same-name collisions by shadowing the global plugin.

        Args:
            project_root: Project root containing ``.agents/plugins``.
            project_id: Project identifier recorded on project-scoped plugins.

        Returns:
            Plugins in stable scan order, including invalid ones with issues.
        """
        project_root_path = pathlib.Path(project_root).expanduser().resolve()
        plugins = self._scan(self.user_dir, "global", None)
        plugins.extend(
            self._scan(
                project_root_path / ".agents" / "plugins",
                "project",
                project_id,
            )
        )
        return plugins

    def _scan(
        self,
        root: pathlib.Path,
        scope: PluginScope,
        project_id: str | None,
    ) -> list[LoadedPlugin]:
        root = root.expanduser().resolve()
        if not root.is_dir():
            return []
        plugins: list[LoadedPlugin] = []
        for entry in sorted(root.iterdir(), key=lambda item: item.name):
            if not entry.is_dir() or not (entry / "plugin.json").is_file():
                continue
            plugins.append(self._load_plugin(entry, scope, project_id))
        return plugins

    def _load_plugin(
        self,
        root: pathlib.Path,
        scope: PluginScope,
        project_id: str | None,
    ) -> LoadedPlugin:
        root = root.resolve()
        issues: list[PluginIssue] = []
        manifest = _load_manifest(root, issues)
        if manifest is None:
            return LoadedPlugin(
                manifest=None,
                root=root,
                scope=scope,
                project_id=project_id,
                issues=tuple(issues),
            )
        data_root = self.data_dir / manifest.name
        skills = _load_skills(root, manifest.name, issues)
        mcp_servers = _load_mcp(root, data_root, issues)
        hooks, hook_issues = load_plugin_hooks(root, data_root)
        issues.extend(
            PluginIssue(issue.severity, issue.component, issue.message)
            for issue in hook_issues
        )
        return LoadedPlugin(
            manifest=manifest,
            root=root,
            scope=scope,
            project_id=project_id,
            skills=skills,
            mcp_servers=mcp_servers,
            hooks=hooks,
            issues=tuple(issues),
        )
