import pathlib
import re
import shutil
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from skills_ref import validate
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_api.skills import discover_skills
from agentbox_models.tables.core import Project

router = APIRouter(prefix="/skills", tags=["skills"])

_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class SkillWrite(BaseModel):
    description: str
    body: str


def _user_dir(request: Request) -> pathlib.Path:
    return pathlib.Path(request.app.state.settings.skills_user_dir).expanduser()


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
    root = await _project_root(request, project_id)
    skills = discover_skills(root, str(_user_dir(request)))
    return [
        {"name": s.name, "description": s.description, "scope": s.scope} for s in skills
    ]


@router.get("/{name}")
async def get_skill(
    name: str,
    request: Request,
    project_id: str | None = None,
    _=Depends(require_permission("agents:read")),
):
    root = await _project_root(request, project_id)
    skill = next(
        (s for s in discover_skills(root, str(_user_dir(request))) if s.name == name),
        None,
    )
    if skill is None:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "name": skill.name,
        "description": skill.description,
        "scope": skill.scope,
        "body": skill.location.read_text(encoding="utf-8"),
    }


@router.put("/{name}")
async def save_skill(
    name: str,
    body: SkillWrite,
    request: Request,
    _=Depends(require_permission("agents:create")),
):
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
    target = _user_dir(request) / name
    if not (target / "SKILL.md").is_file():
        raise HTTPException(status_code=404, detail="Not found")
    shutil.rmtree(target)
    return {"ok": True}
