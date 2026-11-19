import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel

from agentbox_api.deps import require_permission
from agentbox_models.repos.crud import ProjectRepository
from agentbox_models.tables.core import Project

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    path: str


@router.post("", response_model=Project)
async def create_project(
    body: ProjectCreate, request: Request, _=Depends(require_permission("projects:create"))
):
    project = Project(
        id=uuid.uuid4().hex,
        name=body.name,
        path=body.path,
        owner_id=request.user.identity,
    )
    project = await ProjectRepository(request.app.state.session_factory).create(project)
    logger.info("project created project={}", project.id)
    return project


@router.get("", response_model=list[Project])
async def list_projects(request: Request, _=Depends(require_permission("projects:read"))):
    return await ProjectRepository(request.app.state.session_factory).list()


@router.get("/{pid}", response_model=Project)
async def get_project(pid: str, request: Request, _=Depends(require_permission("projects:read"))):
    p = await ProjectRepository(request.app.state.session_factory).get(pid)
    if p is None:
        raise HTTPException(status_code=404, detail="Not found")
    return p


@router.delete("/{pid}")
async def delete_project(
    pid: str, request: Request, _=Depends(require_permission("projects:delete"))
):
    await ProjectRepository(request.app.state.session_factory).delete(pid)
    logger.info("project deleted project={}", pid)
    return {"ok": True}
