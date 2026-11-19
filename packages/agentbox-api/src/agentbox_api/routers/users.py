import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_api.security import hash_password
from agentbox_models.repos.crud import UserRepository
from agentbox_models.tables.auth import (
    ApiKey,
    Role,
    User,
    UserRoleLink,
)

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    username: str
    email: str
    password: str


class UserUpdate(BaseModel):
    email: str | None = None
    is_active: bool | None = None
    password: str | None = None


class RoleIds(BaseModel):
    role_ids: list[str] = []


class UserRead(BaseModel):
    id: str
    username: str
    email: str
    is_active: bool


class RoleRead(BaseModel):
    id: str
    name: str
    description: str | None = None


@router.post("", response_model=UserRead)
async def create_user(
    body: UserCreate, request: Request, _=Depends(require_permission("users:manage"))
):
    async with request.app.state.session_factory() as s:
        existing = (
            await s.execute(select(User).where(User.username == body.username))
        ).scalars().first()
        if existing is not None:
            raise HTTPException(status_code=409, detail="Username already exists")
        user = User(
            id=uuid.uuid4().hex,
            username=body.username,
            email=body.email,
            password_hash=hash_password(body.password),
        )
        s.add(user)
        await s.commit()
        await s.refresh(user)
    return user


@router.get("", response_model=list[UserRead])
async def list_users(request: Request, _=Depends(require_permission("users:manage"))):
    return await UserRepository(request.app.state.session_factory).list()


@router.put("/{uid}", response_model=UserRead)
async def update_user(
    uid: str,
    body: UserUpdate,
    request: Request,
    _=Depends(require_permission("users:manage")),
):
    async with request.app.state.session_factory() as s:
        user = (await s.execute(select(User).where(User.id == uid))).scalars().first()
        if user is None:
            raise HTTPException(status_code=404, detail="Not found")
        if body.email is not None:
            user.email = body.email
        if body.is_active is not None:
            user.is_active = body.is_active
        if body.password is not None:
            user.password_hash = hash_password(body.password)
        s.add(user)
        await s.commit()
        await s.refresh(user)
    return user


@router.get("/{uid}/roles", response_model=list[RoleRead])
async def get_user_roles(
    uid: str, request: Request, _=Depends(require_permission("users:manage"))
):
    async with request.app.state.session_factory() as s:
        rows = (
            await s.execute(
                select(Role)
                .join(UserRoleLink, UserRoleLink.role_id == Role.id)
                .where(UserRoleLink.user_id == uid)
            )
        ).scalars().all()
    return rows


@router.put("/{uid}/roles", response_model=list[RoleRead])
async def set_user_roles(
    uid: str,
    body: RoleIds,
    request: Request,
    _=Depends(require_permission("users:manage")),
):
    async with request.app.state.session_factory() as s:
        user = (await s.execute(select(User).where(User.id == uid))).scalars().first()
        if user is None:
            raise HTTPException(status_code=404, detail="Not found")
        if body.role_ids:
            found = (
                await s.execute(select(Role.id).where(Role.id.in_(body.role_ids)))  # ty: ignore[missing-attribute]
            ).scalars().all()
            if set(found) != set(body.role_ids):
                raise HTTPException(status_code=400, detail="Unknown role id")
        await s.execute(delete(UserRoleLink).where(UserRoleLink.user_id == uid))
        for rid in body.role_ids:
            s.add(UserRoleLink(user_id=uid, role_id=rid))
        await s.commit()
        rows = (
            await s.execute(
                select(Role)
                .join(UserRoleLink, UserRoleLink.role_id == Role.id)
                .where(UserRoleLink.user_id == uid)
            )
        ).scalars().all()
    return rows


@router.delete("/{uid}")
async def delete_user(
    uid: str, request: Request, _=Depends(require_permission("users:manage"))
):
    async with request.app.state.session_factory() as s:
        user = (await s.execute(select(User).where(User.id == uid))).scalars().first()
        if user is not None:
            await s.execute(delete(UserRoleLink).where(UserRoleLink.user_id == uid))
            await s.execute(delete(ApiKey).where(ApiKey.user_id == uid))
            await s.delete(user)
            await s.commit()
    return {"ok": True}
