"""Role endpoints.

Roles bundle permissions and are assigned to users. All role management
requires the ``roles:manage`` permission.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, field_validator
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_api.validation import required_name
from agentbox_models.repos.crud import RoleRepository
from agentbox_models.tables.auth import (
    Permission,
    Role,
    RolePermissionLink,
    UserRoleLink,
)

router = APIRouter(prefix="/roles", tags=["roles"])


class RoleCreate(BaseModel):
    """Request body for creating a role."""

    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return required_name(value)


class RoleUpdate(BaseModel):
    """Request body that updates a role's name or description."""

    name: str | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return required_name(value) if value is not None else None


class PermissionIds(BaseModel):
    """Request body that replaces a role's permission set."""

    permission_ids: list[str] = []


# Keep this docstring identical to the PermissionRead in routers/permissions.py
# so FastAPI's component names and the generated API types stay stable.
class PermissionRead(BaseModel):
    """A permission record."""

    id: str
    name: str
    description: str | None = None


# Keep this docstring identical to the RoleRead in routers/users.py so FastAPI's
# component names and the generated API types stay stable.
class RoleRead(BaseModel):
    """A role record."""

    id: str
    name: str
    description: str | None = None


@router.post("", response_model=RoleRead)
async def create_role(
    body: RoleCreate, request: Request, _=Depends(require_permission("roles:manage"))
):
    """Create a role.

    Requires the ``roles:manage`` permission.

    Returns:
        The created role.
    """
    repo = RoleRepository(request.app.state.session_factory)
    role = await repo.create(
        Role(id=uuid.uuid4().hex, name=body.name, description=body.description)
    )
    logger.info("role created name={}", role.name)
    return role


@router.get("", response_model=list[RoleRead])
async def list_roles(request: Request, _=Depends(require_permission("roles:manage"))):
    """List roles.

    Requires the ``roles:manage`` permission.

    Returns:
        All roles.
    """
    return await RoleRepository(request.app.state.session_factory).list()


@router.put("/{rid}", response_model=RoleRead)
async def update_role(
    rid: str,
    body: RoleUpdate,
    request: Request,
    _=Depends(require_permission("roles:manage")),
):
    """Update a role's name or description.

    Requires the ``roles:manage`` permission.

    Returns:
        The updated role, or 404 when missing and 409 when the new name is taken.
    """
    async with request.app.state.session_factory() as s:
        role = (await s.execute(select(Role).where(Role.id == rid))).scalars().first()
        if role is None:
            raise HTTPException(status_code=404, detail="Not found")
        if body.name is not None:
            dup = (
                await s.execute(
                    select(Role).where(Role.name == body.name, Role.id != rid)
                )
            ).scalars().first()
            if dup is not None:
                raise HTTPException(status_code=409, detail="Role already exists")
            role.name = body.name
        if body.description is not None:
            role.description = body.description
        s.add(role)
        await s.commit()
        await s.refresh(role)
        logger.info("role updated name={}", role.name)
    return role


@router.get("/{rid}/permissions", response_model=list[PermissionRead])
async def get_role_permissions(
    rid: str, request: Request, _=Depends(require_permission("roles:manage"))
):
    """List a role's permissions.

    Requires the ``roles:manage`` permission.

    Returns:
        The permissions granted to the role; empty when the role has none or
        does not exist.
    """
    async with request.app.state.session_factory() as s:
        rows = (
            await s.execute(
                select(Permission)
                .join(RolePermissionLink)
                .where(RolePermissionLink.role_id == rid)
            )
        ).scalars().all()
    return rows


@router.put("/{rid}/permissions", response_model=list[PermissionRead])
async def set_role_permissions(
    rid: str,
    body: PermissionIds,
    request: Request,
    _=Depends(require_permission("roles:manage")),
):
    """Replace a role's permission set.

    Requires the ``roles:manage`` permission. Every id must reference an
    existing permission (400 otherwise).

    Returns:
        The role's resulting permissions, or 404 when the role does not exist.
    """
    async with request.app.state.session_factory() as s:
        role = (await s.execute(select(Role).where(Role.id == rid))).scalars().first()
        if role is None:
            raise HTTPException(status_code=404, detail="Not found")
        if body.permission_ids:
            found = (
                await s.execute(
                    select(Permission.id).where(
                        Permission.id.in_(body.permission_ids)  # ty: ignore[missing-attribute]
                    )
                )
            ).scalars().all()
            if set(found) != set(body.permission_ids):
                raise HTTPException(status_code=400, detail="Unknown permission id")
        existing = (
            await s.execute(
                select(RolePermissionLink).where(RolePermissionLink.role_id == rid)
            )
        ).scalars().all()
        for link in existing:
            await s.delete(link)
        for pid in body.permission_ids:
            s.add(RolePermissionLink(role_id=rid, permission_id=pid))
        await s.commit()
        logger.info("role permissions set role={} count={}", rid, len(body.permission_ids))
        rows = (
            await s.execute(
                select(Permission)
                .join(RolePermissionLink)
                .where(RolePermissionLink.role_id == rid)
            )
        ).scalars().all()
    return rows


@router.delete("/{rid}")
async def delete_role(
    rid: str, request: Request, _=Depends(require_permission("roles:manage"))
):
    """Delete a role and detach it from users and permissions.

    Requires the ``roles:manage`` permission. Deleting a missing role is a
    no-op.

    Returns:
        ``{"ok": True}``.
    """
    async with request.app.state.session_factory() as s:
        role = (await s.execute(select(Role).where(Role.id == rid))).scalars().first()
        if role is not None:
            perm_links = (
                await s.execute(
                    select(RolePermissionLink).where(RolePermissionLink.role_id == rid)
                )
            ).scalars().all()
            for link in perm_links:
                await s.delete(link)
            user_links = (
                await s.execute(
                    select(UserRoleLink).where(UserRoleLink.role_id == rid)
                )
            ).scalars().all()
            for link in user_links:
                await s.delete(link)
            await s.delete(role)
            await s.commit()
            logger.info("role deleted id={}", rid)
    return {"ok": True}

