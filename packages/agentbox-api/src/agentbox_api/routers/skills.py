"""Skill discovery and user-skill management endpoints.

Skills are Markdown instruction bundles discovered from the project, the user
directory, and installed plugins. User-authored skills are written under the
configured skills directory; plugin-provided skills are read-only.
"""

import pathlib
import re
import shutil
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from skills_ref import validate
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_api.plugin_service import PluginService
from agentbox_api.skills import Skill, discover_skills
from agentbox_models.tables.core import Project

router = APIRouter(prefix="/skills", tags=["skills"])

_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class SkillWrite(BaseModel):
    """Request body for writing a user skill's description and body."""

    description: str
    body: str


def _user_dir(request: Request) -> pathlib.Path:
    return pathlib.Path(request.app.state.settings.skills_user_dir).expanduser()


async def _plugin_skills(
    request: Request, project_id: str | None, root: str
) -> list[Skill]:
    settings = request.app.state.settings
    service = PluginService(
        request.app.state.session_factory,
        settings.plugins_user_dir,
        settings.plugins_data_dir,
    )
    return [
        Skill(
            name=item.scoped_name,
            description=item.description,
            location=item.location,
            scope="plugin",
            plugin=item.plugin_name,
        )
        for item in await service.list_plugin_skills(project_id, root)
    ]


async def _project_root(request: Request, project_id: str | None) -> str:
    if not project_id:
        return "."
    async with request.app.state.session_factory() as s:
        project = (
            await s.execute(select(Project).where(Project.id == project_id))
        ).scalars().first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.path


@router.get("")
async def list_skills(
    request: Request,
    project_id: str | None = None,
    _=Depends(require_permission("agents:read")),
):
    """List skills available to a project.

    Requires the ``agents:read`` permission. Passing ``project_id`` includes
    project-scoped skills and plugins.

    Returns:
        Skill summaries, or 404 when ``project_id`` does not exist.
    """
    root = await _project_root(request, project_id)
    skills = discover_skills(
        root,
        str(_user_dir(request)),
        await _plugin_skills(request, project_id, root),
    )
    return [
        {
            "name": s.name,
            "description": s.description,
            "scope": s.scope,
            "plugin": s.plugin,
        }
        for s in skills
    ]


@router.get("/{name}")
async def get_skill(
    name: str,
    request: Request,
    project_id: str | None = None,
    _=Depends(require_permission("agents:read")),
):
    """Get one skill including its Markdown body.

    Requires the ``agents:read`` permission.

    Returns:
        The skill detail, or 404 when the project or skill is not found.
    """
    root = await _project_root(request, project_id)
    skills = discover_skills(
        root,
        str(_user_dir(request)),
        await _plugin_skills(request, project_id, root),
    )
    skill = next((s for s in skills if s.name == name), None)
    if skill is None:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "name": skill.name,
        "description": skill.description,
        "scope": skill.scope,
        "plugin": skill.plugin,
        "body": skill.location.read_text(encoding="utf-8"),
    }


@router.put("/{name}")
async def save_skill(
    name: str,
    body: SkillWrite,
    request: Request,
    _=Depends(require_permission("agents:create")),
):
    """Create or overwrite a user skill.

    Requires the ``agents:create`` permission. The name must be lowercase
    kebab-case (400 otherwise) and the rendered skill must pass validation (422
    otherwise).

    Returns:
        ``{"ok": True}``.
    """
    if not _NAME.match(name):
        raise HTTPException(status_code=400, detail="Invalid skill name")
    content = (
        f"---\nname: {name}\ndescription: {body.description}\n---\n\n{body.body}\n"
    )
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        d = tmp / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(content, encoding="utf-8")
        errors = validate(d)
        if errors:
            raise HTTPException(
                status_code=422, detail="; ".join(str(e) for e in errors)
            )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    target = _user_dir(request) / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "SKILL.md").write_text(content, encoding="utf-8")
    return {"ok": True}


@router.delete("/{name}")
async def delete_skill(
    name: str, request: Request, _=Depends(require_permission("agents:create"))
):
    """Delete a user skill.

    Requires the ``agents:create`` permission. Plugin-managed skills (names with
    a ``:``) cannot be deleted (400).

    Returns:
        ``{"ok": True}``, or 404 when the user skill does not exist.
    """
    if ":" in name:
        raise HTTPException(status_code=400, detail="Plugin-managed skill")
    target = _user_dir(request) / name
    if not (target / "SKILL.md").is_file():
        raise HTTPException(status_code=404, detail="Not found")
    shutil.rmtree(target)
    return {"ok": True}
