"""Agent Skills: discovery, catalog, activation, and agent preparation."""

from __future__ import annotations

import pathlib
from collections.abc import Callable
from dataclasses import dataclass

from loguru import logger
from skills_ref import read_properties, to_prompt

from agentbox_api.runtime import AgentRuntime, build_registry, resolve_agent_runtime
from agentbox_harness.spec import AgentSpec, NativeToolBinding
from agentbox_harness.tools.registry import ToolRegistry

_BUILTIN = pathlib.Path(__file__).parent / "skills_builtin"


@dataclass
class Skill:
    name: str
    description: str
    location: pathlib.Path
    scope: str


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


def discover_skills(project_root: str, user_dir: str) -> list[Skill]:
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
    logger.debug("skills discovered count={}", len(merged))
    return list(merged.values())


def catalog_instructions(skills: list[Skill]) -> str:
    if not skills:
        return ""
    xml = to_prompt([s.location.parent for s in skills])
    return (
        "The following skills provide specialized instructions for specific tasks. "
        "When a task matches a skill's description, call activate_skill with the "
        "skill's name before proceeding. Relative paths in a skill resolve against "
        "its directory.\n\n" + xml
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


async def prepare_agent(
    factory,
    agent_name: str,
    project_root: str,
    user_dir: str,
    media_max_dimension: int = 1568,
    media_max_bytes: int = 1_500_000,
) -> PreparedAgent:
    runtime = await resolve_agent_runtime(factory, agent_name)
    skills = discover_skills(project_root, user_dir)
    spec = augment_spec(runtime.spec, skills)
    extra_tools = {"activate_skill": make_activate_tool(skills)} if skills else None
    registry = build_registry(
        project_root,
        extra_read_roots=[s.location.parent for s in skills],
        extra_tools=extra_tools,
        media_max_dimension=media_max_dimension,
        media_max_bytes=media_max_bytes,
    )
    return PreparedAgent(runtime, spec, registry, skills)
