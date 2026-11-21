import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, field_validator
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_api.runtime import delete_session_data
from agentbox_api.validation import checked_directory, checked_extra_roots, required_name
from agentbox_models.repos.crud import ProjectRepository
from agentbox_models.tables.core import Project, SessionRow

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    path: str
    extra_roots: list[str] = []

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return required_name(value)

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        return checked_directory(value)

    @field_validator("extra_roots")
    @classmethod
    def _roots(cls, value: list[str]) -> list[str]:
        return checked_extra_roots(value)


class ProjectUpdate(BaseModel):
    name: str | None = None
    extra_roots: list[str] | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return required_name(value) if value is not None else None

    @field_validator("extra_roots")
    @classmethod
    def _roots(cls, value: list[str] | None) -> list[str] | None:
        return checked_extra_roots(value) if value is not None else None


@router.post("", response_model=Project)
async def create_project(
    body: ProjectCreate, request: Request, _=Depends(require_permission("projects:create"))
):
    project = Project(
        id=uuid.uuid4().hex,
        name=body.name,
        path=body.path,
        owner_id=request.user.identity,
        extra_roots=body.extra_roots,
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


@router.put("/{pid}", response_model=Project)
async def update_project(
    pid: str,
    body: ProjectUpdate,
    request: Request,
    _=Depends(require_permission("projects:create")),
):
    factory = request.app.state.session_factory
    async with factory() as s:
        project = await s.get(Project, pid)
        if project is None:
            raise HTTPException(status_code=404, detail="Not found")
        if body.name is not None:
            project.name = body.name
        if body.extra_roots is not None:
            project.extra_roots = body.extra_roots
        s.add(project)
        await s.commit()
        await s.refresh(project)
    logger.info("project updated project={}", pid)
    return project


@router.delete("/{pid}")
async def delete_project(
    pid: str, request: Request, _=Depends(require_permission("projects:delete"))
):
    factory = request.app.state.session_factory
    async with factory() as s:
        session_ids = list(
            (
                await s.execute(
                    select(SessionRow.id).where(SessionRow.project_id == pid)
                )
            )
            .scalars()
            .all()
        )
    for sid in session_ids:
        await delete_session_data(factory, sid)
    await ProjectRepository(factory).delete(pid)
    logger.info("project deleted project={}", pid)
    return {"ok": True}
