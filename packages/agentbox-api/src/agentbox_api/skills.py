"""Agent Skills: discovery, catalog, activation, and agent preparation."""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import Callable
from dataclasses import dataclass, field

from loguru import logger
from skills_ref import read_properties, to_prompt

from agentbox_api.plan_tools import PLAN_TOOL_NAMES, make_plan_tools
from agentbox_api.plugin_service import PluginService
from agentbox_api.project_instructions import (
    build_system_instruction_block,
    make_project_instructions_hook,
)
from agentbox_api.runtime import AgentRuntime, build_registry, resolve_agent_runtime
from agentbox_api.templating import build_context, render_prompt
from agentbox_harness.compaction import CompactionConfig
from agentbox_harness.context_editing import ContextEditingConfig
from agentbox_harness.lsp.diagnostics import (
    get_diagnostics_service,
    make_lsp_diagnostics_tool,
    make_lsp_notify_hook,
)
from agentbox_harness.lsp.manager import get_lsp_manager
from agentbox_harness.spec import (
    AgentSpec,
    McpToolBinding,
    NativeToolBinding,
)
from agentbox_harness.subagent_sessions import SubagentSessionRunner
from agentbox_harness.tools.registry import ToolRegistry
from agentbox_harness.tools.terminal import (
    TERMINAL_TOOL_NAMES,
    get_job_manager,
    make_terminal_tools,
)
from agentbox_harness.tools.web import WebToolConfig
from agentbox_models.tables.auth import User

_BUILTIN = pathlib.Path(__file__).parent / "skills_builtin"


@dataclass
class Skill:
    name: str
    description: str
    location: pathlib.Path
    scope: str
    plugin: str | None = None


def _scan(directory: pathlib.Path, scope: str) -> list[Skill]:
    if not directory.is_dir():
        return []
    out: list[Skill] = []
    for entry in sorted(directory.iterdir()):
        skill_md = entry / "SKILL.md"
        if not (entry.is_dir() and skill_md.is_file()):
            continue
        try:
            props = read_properties(entry)
        except Exception:
            continue
        if getattr(props, "description", None):
            out.append(Skill(props.name, props.description, skill_md, scope))
    return out


def discover_skills(
    project_root: str,
    user_dir: str,
    extra_skills: list[Skill] | None = None,
) -> list[Skill]:
    scopes = {
        "builtin": _scan(_BUILTIN, "builtin"),
        "user": _scan(pathlib.Path(user_dir).expanduser(), "user"),
        "project": _scan(
            pathlib.Path(project_root) / ".agents" / "skills", "project"
        ),
    }
    merged: dict[str, Skill] = {}
    for scope in ("builtin", "user", "project"):
        for skill in scopes[scope]:
            merged[skill.name] = skill
    for skill in extra_skills or []:
        merged[skill.name] = skill
    logger.debug("skills discovered count={}", len(merged))
    return list(merged.values())


def catalog_instructions(skills: list[Skill]) -> str:
    if not skills:
        return ""
    regular = [s for s in skills if s.scope != "plugin"]
    plugin = [s for s in skills if s.scope == "plugin"]
    blocks: list[str] = []
    if regular:
        blocks.append(to_prompt([s.location.parent for s in regular]))
    if plugin:
        lines = [
            "Plugin-provided skills (activate by their full namespaced name):"
        ]
        lines.extend(
            f"- {s.name} — {s.description}" for s in plugin
        )
        blocks.append("\n".join(lines))
    return (
        "The following skills provide specialized instructions for specific tasks. "
        "When a task matches a skill's description, call activate_skill with the "
        "skill's name before proceeding. Relative paths in a skill resolve against "
        "its directory.\n\n" + "\n\n".join(blocks)
    )


def augment_spec(spec: AgentSpec, skills: list[Skill]) -> AgentSpec:
    if not skills:
        return spec
    return spec.model_copy(
        update={
            "instructions": spec.instructions + "\n\n" + catalog_instructions(skills),
            "tool_bindings": [
                *spec.tool_bindings,
                NativeToolBinding(name="activate_skill"),
            ],
        }
    )


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].strip()
    return text


def render_skill(skill: Skill) -> str:
    base = skill.location.parent
    body = _strip_frontmatter(skill.location.read_text(encoding="utf-8"))
    resources = sorted(
        p.relative_to(base).as_posix()
        for p in base.rglob("*")
        if p.is_file() and p != skill.location
    )
    listing = "\n".join(resources)
    return (
        f"<skill_content name={skill.name!r}>\n{body}\n\n"
        f"Skill directory: {base}\nResources:\n{listing}\n</skill_content>"
    )


def make_activate_tool(skills: list[Skill]) -> Callable:
    by_name = {s.name: s for s in skills}

    async def activate_skill(name: str) -> str:
        skill = by_name.get(name)
        if skill is None:
            logger.warning("unknown skill name={}", name)
            return (
                f"Unknown skill: {name}. Available: {', '.join(sorted(by_name))}"
            )
        logger.info("skill activated name={}", name)
        return render_skill(skill)

    return activate_skill


@dataclass
class PreparedAgent:
    runtime: AgentRuntime
    spec: AgentSpec
    registry: ToolRegistry
    skills: list[Skill]
    subagent_session_runner: SubagentSessionRunner | None = None
    plugin_roots: list[pathlib.Path] = field(default_factory=list)


def _resolve_extra_roots(
    project_root: str, extra_roots: list[str] | None
) -> list[pathlib.Path]:
    root = pathlib.Path(project_root).expanduser().resolve()
    resolved: list[pathlib.Path] = []
    seen: set[pathlib.Path] = set()
    for value in extra_roots or []:
        text = (value or "").strip()
        if not text:
            continue
        candidate = pathlib.Path(text).expanduser()
        path = (candidate if candidate.is_absolute() else root / candidate).resolve()
        if path not in seen:
            seen.add(path)
            resolved.append(path)
    return resolved


async def prepare_agent(
    factory,
    agent_name: str,
    project_root: str,
    user_dir: str,
    user_name: str | None = None,
    session_id: str | None = None,
    session_mode: str | None = None,
    media_max_dimension: int = 1568,
    media_max_bytes: int = 1_500_000,
    web_config: WebToolConfig | None = None,
    extra_roots: list[str] | None = None,
    compaction: CompactionConfig | None = None,
    context_editing: ContextEditingConfig | None = None,
    project_id: str | None = None,
    plugins_user_dir: str | None = None,
    plugins_data_dir: str | None = None,
    subagent_session_depth: int = 0,
) -> PreparedAgent:
    runtime = await resolve_agent_runtime(factory, agent_name)
    resolved_extra = _resolve_extra_roots(project_root, extra_roots)
    plugin_skills: list[Skill] = []
    plugin_roots: list[pathlib.Path] = []
    plugin_service: PluginService | None = None
    if plugins_user_dir and plugins_data_dir:
        plugin_service = PluginService(
            factory, plugins_user_dir, plugins_data_dir
        )
        plugin_skills = [
            Skill(
                name=item.scoped_name,
                description=item.description,
                location=item.location,
                scope="plugin",
                plugin=item.plugin_name,
            )
            for item in await plugin_service.list_plugin_skills(
                project_id, project_root
            )
        ]
        plugin_roots = await plugin_service.plugin_roots(
            project_id, project_root
        )
    skills = discover_skills(project_root, user_dir, plugin_skills)
    resolved_user = user_name
    if resolved_user is None and runtime.created_by:
        async with factory() as s:
            owner = await s.get(User, runtime.created_by)
            resolved_user = owner.username if owner else None
    context = build_context(
        agent_name=runtime.spec.name,
        agent_description=runtime.spec.description,
        project_root=project_root,
        user_name=resolved_user,
        session_id=session_id,
        session_mode=session_mode,
        model_name=runtime.spec.model_binding.model,
        model_provider=runtime.spec.model_binding.provider,
        skills=skills,
    )
    rendered = render_prompt(runtime.spec.instructions, context, agent=agent_name)
    spec = runtime.spec.model_copy(update={"instructions": rendered})
    spec = augment_spec(spec, skills)
    if plugin_service is not None:
        resolved_bindings: list[McpToolBinding] = []
        seen_ids = {
            binding.id
            for binding in spec.tool_bindings
            if isinstance(binding, McpToolBinding) and binding.id
        }
        for reference in spec.plugin_mcp_bindings:
            if reference.project_id is not None and (
                reference.project_id != project_id
            ):
                continue
            resolved = await plugin_service.resolve_mcp(
                reference.plugin,
                reference.server,
                project_id,
                project_root,
            )
            if resolved is None:
                logger.warning(
                    "plugin mcp unavailable plugin={} server={}",
                    reference.plugin,
                    reference.server,
                )
                continue
            if resolved.id in seen_ids:
                logger.warning("duplicate plugin mcp id={}", resolved.id)
                continue
            seen_ids.add(resolved.id)
            resolved_bindings.append(
                McpToolBinding(
                    id=resolved.id,
                    server_url=resolved.url,
                    command=resolved.command,
                    args=list(resolved.args),
                    env=resolved.env,
                    env_passthrough=list(resolved.env_passthrough),
                    cwd=resolved.cwd,
                    transport=resolved.transport,
                    headers=resolved.headers,
                )
            )
        if resolved_bindings:
            spec = spec.model_copy(
                update={
                    "tool_bindings": [
                        *spec.tool_bindings,
                        *resolved_bindings,
                    ]
                }
            )
    instruction_block = build_system_instruction_block(project_root, session_id)
    if instruction_block:
        spec = spec.model_copy(
            update={"instructions": spec.instructions + "\n\n" + instruction_block}
        )
    manager = get_lsp_manager()
    service = get_diagnostics_service()
    lsp_active = bool(session_id and manager.enabled and service.enabled)
    if lsp_active and service.warm_on_start:
        asyncio.create_task(manager.warm(project_root))
    if session_id:
        existing = {
            binding.name
            for binding in spec.tool_bindings
            if isinstance(binding, NativeToolBinding)
        }
        additions = [
            NativeToolBinding(name=name)
            for name in PLAN_TOOL_NAMES
            if name not in existing
        ]
        if lsp_active and "lsp_diagnostics" not in existing:
            additions.append(NativeToolBinding(name="lsp_diagnostics"))
        if additions:
            spec = spec.model_copy(
                update={"tool_bindings": [*spec.tool_bindings, *additions]}
            )
    extra_tools = {"activate_skill": make_activate_tool(skills)} if skills else {}
    if session_id:
        extra_tools.update(make_plan_tools(factory, session_id))
    if lsp_active:
        extra_tools["lsp_diagnostics"] = make_lsp_diagnostics_tool(
            service, session_id, project_root
        )
    hooks = []
    if lsp_active and service.mode == "auto":
        hooks.append(make_lsp_notify_hook(service, session_id, project_root))
    if session_id:
        hooks.append(make_project_instructions_hook(project_root, session_id))
    registry = build_registry(
        project_root,
        extra_read_roots=[
            *[s.location.parent for s in skills],
            *plugin_roots,
        ],
        extra_tools=extra_tools or None,
        hooks=hooks,
        media_max_dimension=media_max_dimension,
        media_max_bytes=media_max_bytes,
        web_config=web_config,
        extra_write_roots=resolved_extra,
    )
    native_names = {
        binding.name
        for binding in spec.tool_bindings
        if isinstance(binding, NativeToolBinding)
    }
    if session_id and native_names & set(TERMINAL_TOOL_NAMES):
        additions = [
            NativeToolBinding(name=name)
            for name in TERMINAL_TOOL_NAMES
            if name not in native_names
        ]
        if additions:
            spec = spec.model_copy(
                update={"tool_bindings": [*spec.tool_bindings, *additions]}
            )
        terminal_tools = make_terminal_tools(
            get_job_manager(),
            session_id,
            project_root,
            [pathlib.Path(project_root).expanduser().resolve(), *resolved_extra],
        )
        for name, fn in terminal_tools.items():
            registry.register_native(name, fn, required_flags=("write",))

    from agentbox_api.subagent_sessions import (
        ApiSubagentSessionRunner,
        SubagentSessionContext,
    )

    subagent_session_runner = ApiSubagentSessionRunner(
        SubagentSessionContext(
            factory=factory,
            project_root=project_root,
            skills_user_dir=user_dir,
            extra_roots=[str(path) for path in resolved_extra],
            web_config=web_config,
            compaction=compaction or CompactionConfig(),
            context_editing=context_editing,
            project_id=project_id,
            plugins_user_dir=plugins_user_dir,
            plugins_data_dir=plugins_data_dir,
            media_max_dimension=media_max_dimension,
            media_max_bytes=media_max_bytes,
            depth=subagent_session_depth,
        )
    )
    return PreparedAgent(
        runtime,
        spec,
        registry,
        skills,
        subagent_session_runner,
        plugin_roots=plugin_roots,
    )
