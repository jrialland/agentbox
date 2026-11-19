import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_models.tables.auth import Permission, RolePermissionLink

router = APIRouter(prefix="/permissions", tags=["permissions"])

_NAME_RE = re.compile(r"[a-z0-9_]+:[a-z0-9_-]+")


class PermissionRead(BaseModel):
    id: str
    name: str
    description: str | None = None


class PermissionCreate(BaseModel):
    name: str
    description: str | None = None


class PermissionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


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
    async with request.app.state.session_factory() as s:
        rows = (await s.execute(select(Permission))).scalars().all()
    return rows


@router.post("", response_model=PermissionRead)
async def create_permission(
    body: PermissionCreate,
    request: Request,
    _=Depends(require_permission("roles:manage")),
):
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
    return perm


@router.put("/{pid}", response_model=PermissionRead)
async def update_permission(
    pid: str,
    body: PermissionUpdate,
    request: Request,
    _=Depends(require_permission("roles:manage")),
):
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
    return perm


@router.delete("/{pid}")
async def delete_permission(
    pid: str, request: Request, _=Depends(require_permission("roles:manage"))
):
    async with request.app.state.session_factory() as s:
        perm = await _get_or_404(s, pid)
        await s.execute(
            delete(RolePermissionLink).where(RolePermissionLink.permission_id == pid)
        )
        await s.delete(perm)
        await s.commit()
    return {"ok": True}
