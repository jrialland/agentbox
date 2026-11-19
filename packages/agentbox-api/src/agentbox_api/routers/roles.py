import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_models.repos.crud import RoleRepository
from agentbox_models.tables.auth import (
    Permission,
    Role,
    RolePermissionLink,
    UserRoleLink,
)

router = APIRouter(prefix="/roles", tags=["roles"])


class RoleCreate(BaseModel):
    name: str
    description: str | None = None


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class PermissionIds(BaseModel):
    permission_ids: list[str] = []


class PermissionRead(BaseModel):
    id: str
    name: str
    description: str | None = None


class RoleRead(BaseModel):
    id: str
    name: str
    description: str | None = None


@router.post("", response_model=RoleRead)
async def create_role(
    body: RoleCreate, request: Request, _=Depends(require_permission("roles:manage"))
):
    repo = RoleRepository(request.app.state.session_factory)
    return await repo.create(
        Role(id=uuid.uuid4().hex, name=body.name, description=body.description)
    )


@router.get("", response_model=list[RoleRead])
async def list_roles(request: Request, _=Depends(require_permission("roles:manage"))):
    return await RoleRepository(request.app.state.session_factory).list()


@router.put("/{rid}", response_model=RoleRead)
async def update_role(
    rid: str,
    body: RoleUpdate,
    request: Request,
    _=Depends(require_permission("roles:manage")),
):
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
    return role


@router.get("/{rid}/permissions", response_model=list[PermissionRead])
async def get_role_permissions(
    rid: str, request: Request, _=Depends(require_permission("roles:manage"))
):
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
    return {"ok": True}

