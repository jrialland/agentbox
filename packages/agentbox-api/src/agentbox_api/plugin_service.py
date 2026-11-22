from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

from sqlmodel import select

from agentbox_api.plugin_catalog import (
    LoadedPlugin,
    PluginCatalog,
    PluginIssue,
    PluginMcpServer,
    PluginSkill,
)
from agentbox_api.plugin_hook_config import PluginHook
from agentbox_models.tables.core import PluginState, utcnow

_ENV_PASSTHROUGH = (
    "PATH",
    "PATHEXT",
    "SystemRoot",
    "WINDIR",
    "HOME",
    "USERPROFILE",
    "TEMP",
    "TMP",
)


def _state_id(plugin_name: str, scope: str, project_id: str | None) -> str:
    if scope == "global":
        return f"global:{plugin_name}"
    return f"project:{project_id}:{plugin_name}"


@dataclass(frozen=True)
class ResolvedPluginMcp:
    plugin: str
    server: str
    project_id: str | None
    id: str
    transport: str
    command: str = ""
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    env_passthrough: tuple[str, ...] = ()
    cwd: str = ""
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginView:
    loaded: LoadedPlugin
    enabled: bool
    shadowed: bool = False

    @property
    def name(self) -> str:
        if self.loaded.manifest is not None:
            return self.loaded.manifest.name
        return self.loaded.root.name

    @property
    def valid(self) -> bool:
        return self.loaded.manifest is not None

    @property
    def scope(self) -> str:
        return self.loaded.scope

    @property
    def project_id(self) -> str | None:
        return self.loaded.project_id

    @property
    def version(self) -> str:
        return self.loaded.manifest.version if self.loaded.manifest else ""

    @property
    def description(self) -> str:
        return self.loaded.manifest.description if self.loaded.manifest else ""

    @property
    def skills(self) -> tuple[PluginSkill, ...]:
        return self.loaded.skills

    @property
    def mcp_servers(self) -> tuple[PluginMcpServer, ...]:
        return self.loaded.mcp_servers

    @property
    def hooks(self) -> tuple[PluginHook, ...]:
        return self.loaded.hooks

    @property
    def issues(self) -> tuple[PluginIssue, ...]:
        return self.loaded.issues


class PluginService:
    def __init__(self, factory, user_dir: str, data_dir: str):
        self.factory = factory
        self.catalog = PluginCatalog(user_dir, data_dir)
        self.data_dir = pathlib.Path(data_dir).expanduser()

    async def list_plugins(
        self, project_id: str | None, project_root: str
    ) -> list[PluginView]:
        loaded = self.catalog.discover(project_root, project_id)
        state = await self._state_map()
        project_by_name = {
            item.manifest.name: item
            for item in loaded
            if item.scope == "project" and item.manifest is not None
        }
        shadowed_names = {
            name
            for name, item in project_by_name.items()
            if _state_id(name, "project", project_id) in state
            and state[_state_id(name, "project", project_id)]
        }
        views = []
        for item in loaded:
            if item.manifest is None:
                views.append(PluginView(loaded=item, enabled=False))
                continue
            name = item.manifest.name
            if item.scope == "global":
                enabled = bool(state.get(_state_id(name, "global", None)))
                views.append(
                    PluginView(
                        loaded=item,
                        enabled=enabled and name not in shadowed_names,
                        shadowed=name in shadowed_names,
                    )
                )
            else:
                enabled = bool(
                    state.get(_state_id(name, "project", project_id))
                )
                views.append(PluginView(loaded=item, enabled=enabled))
        return views

    async def set_enabled(
        self,
        plugin_name: str,
        scope: str,
        project_id: str | None,
        enabled: bool,
        project_root: str,
    ) -> PluginView:
        if scope not in {"global", "project"}:
            raise ValueError(f"invalid plugin scope: {scope}")
        if scope == "project" and not project_id:
            raise ValueError("project_id is required for project plugins")
        if scope == "global":
            project_id = None
        views = await self.list_plugins(project_id, project_root)
        view = next(
            (
                item
                for item in views
                if item.name == plugin_name and item.scope == scope
            ),
            None,
        )
        if view is None or not view.valid:
            raise ValueError(f"plugin not found: {plugin_name}")
        state_id = _state_id(plugin_name, scope, project_id)
        async with self.factory() as s:
            row = await s.get(PluginState, state_id)
            if row is None:
                row = PluginState(
                    id=state_id,
                    plugin_name=plugin_name,
                    scope=scope,
                    project_id=project_id,
                    enabled=enabled,
                )
            else:
                row.enabled = enabled
                row.updated_at = utcnow()
            s.add(row)
            await s.commit()
        views = await self.list_plugins(project_id, project_root)
        return next(
            item
            for item in views
            if item.name == plugin_name and item.scope == scope
        )

    async def enabled_plugins(
        self, project_id: str | None, project_root: str
    ) -> list[LoadedPlugin]:
        return [
            view.loaded
            for view in await self.list_plugins(project_id, project_root)
            if view.enabled and view.valid
        ]

    async def list_plugin_skills(
        self, project_id: str | None, project_root: str
    ) -> list[PluginSkill]:
        skills: list[PluginSkill] = []
        for plugin in await self.enabled_plugins(project_id, project_root):
            skills.extend(plugin.skills)
        return skills

    async def plugin_roots(
        self, project_id: str | None, project_root: str
    ) -> list[pathlib.Path]:
        return [
            plugin.root
            for plugin in await self.enabled_plugins(project_id, project_root)
        ]

    async def resolve_mcp(
        self,
        plugin_name: str,
        server_name: str,
        project_id: str | None,
        project_root: str,
    ) -> ResolvedPluginMcp | None:
        plugins = await self.enabled_plugins(project_id, project_root)
        plugin = next(
            (
                item
                for item in plugins
                if item.manifest is not None
                and item.manifest.name == plugin_name
                and (
                    item.project_id is None
                    or item.project_id == project_id
                )
            ),
            None,
        )
        if plugin is None:
            return None
        server = next(
            (item for item in plugin.mcp_servers if item.name == server_name),
            None,
        )
        if server is None:
            return None
        data_root = self.data_dir / plugin_name
        data_root.mkdir(parents=True, exist_ok=True)
        env = dict(server.env)
        if server.transport == "stdio":
            env.update(
                {
                    "PLUGIN_ROOT": str(plugin.root),
                    "PLUGIN_DATA": str(data_root),
                }
            )
        return ResolvedPluginMcp(
            plugin=plugin_name,
            server=server_name,
            project_id=plugin.project_id,
            id=f"{plugin_name}:{server_name}",
            transport=server.transport,
            command=server.command,
            args=server.args,
            env=env,
            env_passthrough=_ENV_PASSTHROUGH if server.transport == "stdio" else (),
            cwd=server.cwd,
            url=server.url,
            headers=server.headers,
        )

    async def _state_map(self) -> dict[str, bool]:
        async with self.factory() as s:
            rows = (await s.execute(select(PluginState))).scalars().all()
        return {row.id: row.enabled for row in rows}
