from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from agentbox_api.deps import require_permission
from agentbox_models.repos.crud import ProjectRepository
from agentbox_models.tables.core import Project

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    id: str
    name: str
    path: str
    owner_id: str


@router.post("")
async def create_project(
    body: ProjectCreate, request: Request, _=Depends(require_permission("projects:create"))
):
    return await ProjectRepository(request.app.state.session_factory).create(
        Project(**body.model_dump())
    )


@router.get("")
async def list_projects(request: Request, _=Depends(require_permission("projects:read"))):
    return await ProjectRepository(request.app.state.session_factory).list()


@router.get("/{pid}")
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
    return {"ok": True}
