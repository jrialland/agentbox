"""Permission catalog endpoints.

Permissions use ``resource:action`` names and are granted to roles. Modifying the
catalog requires the ``roles:manage`` permission.
"""

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, field_validator
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_api.validation import required_name
from agentbox_models.tables.auth import Permission, RolePermissionLink

router = APIRouter(prefix="/permissions", tags=["permissions"])

_NAME_RE = re.compile(r"[a-z0-9_]+:[a-z0-9_-]+")


# Keep this docstring identical to the PermissionRead in routers/roles.py so
# FastAPI's component names and the generated API types stay stable.
class PermissionRead(BaseModel):
    """A permission record."""

    id: str
    name: str
    description: str | None = None


class PermissionCreate(BaseModel):
    """Request body for creating a permission."""

    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return required_name(value)


class PermissionUpdate(BaseModel):
    """Request body that updates a permission's name or description."""

    name: str | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return required_name(value) if value is not None else None


def _validate_name(name: str) -> None:
    if not _NAME_RE.fullmatch(name):
        raise HTTPException(status_code=400, detail="Invalid permission name")


async def _get_or_404(session, pid: str) -> Permission:
    perm = (
        await session.execute(select(Permission).where(Permission.id == pid))
    ).scalars().first()
    if perm is None:
        raise HTTPException(status_code=404, detail="Not found")
    return perm


@router.get("", response_model=list[PermissionRead])
async def list_permissions(
    request: Request, _=Depends(require_permission("roles:manage"))
):
    """List the permission catalog.

    Requires the ``roles:manage`` permission.

    Returns:
        All permissions.
    """
    async with request.app.state.session_factory() as s:
        rows = (await s.execute(select(Permission))).scalars().all()
    return rows


@router.post("", response_model=PermissionRead)
async def create_permission(
    body: PermissionCreate,
    request: Request,
    _=Depends(require_permission("roles:manage")),
):
    """Add a permission to the catalog.

    Requires the ``roles:manage`` permission. The name must match
    ``resource:action`` (400 otherwise).

    Returns:
        The created permission, or 409 when the name already exists.
    """
    _validate_name(body.name)
    async with request.app.state.session_factory() as s:
        existing = (
            await s.execute(select(Permission).where(Permission.name == body.name))
        ).scalars().first()
        if existing is not None:
            raise HTTPException(status_code=409, detail="Permission already exists")
        perm = Permission(
            id=uuid.uuid4().hex, name=body.name, description=body.description
        )
        s.add(perm)
        await s.commit()
        await s.refresh(perm)
        logger.info("permission created name={}", perm.name)
    return perm


@router.put("/{pid}", response_model=PermissionRead)
async def update_permission(
    pid: str,
    body: PermissionUpdate,
    request: Request,
    _=Depends(require_permission("roles:manage")),
):
    """Update a permission's name or description.

    Requires the ``roles:manage`` permission. A changed name is validated (400
    on an invalid format).

    Returns:
        The updated permission, or 404 when missing and 409 when the new name is
        already taken.
    """
    async with request.app.state.session_factory() as s:
        perm = await _get_or_404(s, pid)
        if body.name is not None:
            _validate_name(body.name)
            dup = (
                await s.execute(
                    select(Permission).where(
                        Permission.name == body.name, Permission.id != pid
                    )
                )
            ).scalars().first()
            if dup is not None:
                raise HTTPException(status_code=409, detail="Permission already exists")
            perm.name = body.name
        if body.description is not None:
            perm.description = body.description
        s.add(perm)
        await s.commit()
        await s.refresh(perm)
        logger.info("permission updated name={}", perm.name)
    return perm


@router.delete("/{pid}")
async def delete_permission(
    pid: str, request: Request, _=Depends(require_permission("roles:manage"))
):
    """Delete a permission and detach it from roles.

    Requires the ``roles:manage`` permission.

    Returns:
        ``{"ok": True}``, or 404 when the permission does not exist.
    """
    async with request.app.state.session_factory() as s:
        perm = await _get_or_404(s, pid)
        links = (
            await s.execute(
                select(RolePermissionLink).where(
                    RolePermissionLink.permission_id == pid
                )
            )
        ).scalars().all()
        for link in links:
            await s.delete(link)
        await s.delete(perm)
        await s.commit()
        logger.info("permission deleted id={}", pid)
    return {"ok": True}
