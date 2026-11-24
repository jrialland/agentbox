"""Project endpoints.

A project names a workspace directory that sessions run against. Paths are
validated against the server's filesystem, and deleting a project also removes
its sessions and their stored data.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, field_validator
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_api.runtime import delete_session_data
from agentbox_api.validation import checked_directory, checked_extra_roots, required_name
from agentbox_models.repos.crud import ProjectRepository
from agentbox_models.repos.project_roots import load_extra_roots, replace_extra_roots
from agentbox_models.tables.core import Project, SessionRow

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    """Request body for creating a project.

    ``path`` must be an existing directory on the server, and every
    ``extra_roots`` entry must be an absolute existing directory.
    """

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
    """Request body that updates a project's name or extra roots."""

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


class ProjectRead(BaseModel):
    """A project and its workspace paths."""

    id: str
    name: str
    path: str
    owner_id: str
    extra_roots: list[str]
    created_at: datetime


def _read(project: Project, extra_roots: list[str]) -> ProjectRead:
    return ProjectRead(
        id=project.id,
        name=project.name,
        path=project.path,
        owner_id=project.owner_id,
        extra_roots=extra_roots,
        created_at=project.created_at,
    )


@router.post("", response_model=ProjectRead)
async def create_project(
    body: ProjectCreate, request: Request, _=Depends(require_permission("projects:create"))
):
    """Create a project owned by the caller.

    Requires the ``projects:create`` permission. Invalid names or paths fail
    validation with 422.

    Returns:
        The created project.
    """
    factory = request.app.state.session_factory
    async with factory() as s:
        project = Project(
            id=uuid.uuid4().hex,
            name=body.name,
            path=body.path,
            owner_id=request.user.identity,
        )
        s.add(project)
        await s.flush()
        await replace_extra_roots(s, project.id, body.extra_roots)
        await s.commit()
        await s.refresh(project)
        roots = await load_extra_roots(s, project.id)
    logger.info("project created project={}", project.id)
    return _read(project, roots)


@router.get("", response_model=list[ProjectRead])
async def list_projects(request: Request, _=Depends(require_permission("projects:read"))):
    """List all projects.

    Requires the ``projects:read`` permission.

    Returns:
        Every project with its extra roots.
    """
    factory = request.app.state.session_factory
    async with factory() as s:
        projects = list((await s.execute(select(Project))).scalars().all())
        return [
            _read(project, await load_extra_roots(s, project.id))
            for project in projects
        ]


@router.get("/{pid}", response_model=ProjectRead)
async def get_project(
    pid: str, request: Request, _=Depends(require_permission("projects:read"))
):
    """Get one project by id.

    Requires the ``projects:read`` permission.

    Returns:
        The project, or 404 when it does not exist.
    """
    factory = request.app.state.session_factory
    async with factory() as s:
        project = await s.get(Project, pid)
        if project is None:
            raise HTTPException(status_code=404, detail="Not found")
        roots = await load_extra_roots(s, project.id)
    return _read(project, roots)


@router.put("/{pid}", response_model=ProjectRead)
async def update_project(
    pid: str,
    body: ProjectUpdate,
    request: Request,
    _=Depends(require_permission("projects:create")),
):
    """Update a project's name or extra roots.

    Requires the ``projects:create`` permission. When ``extra_roots`` is sent it
    replaces the existing set and is validated like creation.

    Returns:
        The updated project, or 404 when it does not exist.
    """
    factory = request.app.state.session_factory
    async with factory() as s:
        project = await s.get(Project, pid)
        if project is None:
            raise HTTPException(status_code=404, detail="Not found")
        if body.name is not None:
            project.name = body.name
        if body.extra_roots is not None:
            await replace_extra_roots(s, project.id, body.extra_roots)
        s.add(project)
        await s.commit()
        await s.refresh(project)
        roots = await load_extra_roots(s, project.id)
    logger.info("project updated project={}", pid)
    return _read(project, roots)


@router.delete("/{pid}")
async def delete_project(
    pid: str, request: Request, _=Depends(require_permission("projects:delete"))
):
    """Delete a project together with its sessions and stored data.

    Requires the ``projects:delete`` permission. Deleting a missing project is a
    no-op.

    Returns:
        ``{"ok": True}``.
    """
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
        await delete_session_data(factory, sid, request.app.state.media_store)
    await ProjectRepository(factory).delete(pid)
    logger.info("project deleted project={}", pid)
    return {"ok": True}
