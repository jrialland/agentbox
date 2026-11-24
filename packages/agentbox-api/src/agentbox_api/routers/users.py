"""User administration endpoints.

Managing users, their active state, and their role assignments requires the
``users:manage`` permission.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, field_validator
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_api.security import hash_password
from agentbox_api.validation import required_name, required_password
from agentbox_models.repos.crud import UserRepository
from agentbox_models.tables.auth import (
    ApiKey,
    Role,
    User,
    UserRoleLink,
)

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    """Request body for creating a user."""

    username: str
    email: str
    password: str

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        return required_name(value, "username")

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return required_name(value, "email")

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        return required_password(value)


class UserUpdate(BaseModel):
    """Request body that updates a user; omitted fields are unchanged."""

    email: str | None = None
    is_active: bool | None = None
    password: str | None = None

    @field_validator("password")
    @classmethod
    def _password(cls, value: str | None) -> str | None:
        return required_password(value) if value is not None else None


class RoleIds(BaseModel):
    """Request body that replaces a user's role set."""

    role_ids: list[str] = []


class UserRead(BaseModel):
    """A user account without its password hash."""

    id: str
    username: str
    email: str
    is_active: bool


# Keep this docstring identical to the RoleRead in routers/roles.py so FastAPI's
# component names and the generated API types stay stable.
class RoleRead(BaseModel):
    """A role record."""

    id: str
    name: str
    description: str | None = None


@router.post("", response_model=UserRead)
async def create_user(
    body: UserCreate, request: Request, _=Depends(require_permission("users:manage"))
):
    """Create a user account.

    Requires the ``users:manage`` permission.

    Returns:
        The created user, or 409 when the username is already taken.
    """
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
        logger.info("user created username={}", user.username)
    return user


@router.get("", response_model=list[UserRead])
async def list_users(request: Request, _=Depends(require_permission("users:manage"))):
    """List user accounts.

    Requires the ``users:manage`` permission.

    Returns:
        All users without password hashes.
    """
    return await UserRepository(request.app.state.session_factory).list()


@router.put("/{uid}", response_model=UserRead)
async def update_user(
    uid: str,
    body: UserUpdate,
    request: Request,
    _=Depends(require_permission("users:manage")),
):
    """Update a user's email, active state, or password.

    Requires the ``users:manage`` permission. Omitted fields are unchanged.

    Returns:
        The updated user, or 404 when it does not exist.
    """
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
        logger.info("user updated username={}", user.username)
    return user


@router.get("/{uid}/roles", response_model=list[RoleRead])
async def get_user_roles(
    uid: str, request: Request, _=Depends(require_permission("users:manage"))
):
    """List a user's roles.

    Requires the ``users:manage`` permission.

    Returns:
        The roles assigned to the user; empty when the user has none or does not
        exist.
    """
    async with request.app.state.session_factory() as s:
        rows = (
            await s.execute(
                select(Role)
                .join(UserRoleLink)
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
    """Replace a user's role assignments.

    Requires the ``users:manage`` permission. Every id must reference an
    existing role (400 otherwise).

    Returns:
        The user's resulting roles, or 404 when the user does not exist.
    """
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
        existing = (
            await s.execute(select(UserRoleLink).where(UserRoleLink.user_id == uid))
        ).scalars().all()
        for link in existing:
            await s.delete(link)
        for rid in body.role_ids:
            s.add(UserRoleLink(user_id=uid, role_id=rid))
        await s.commit()
        logger.info("user roles set user={} count={}", uid, len(body.role_ids))
        rows = (
            await s.execute(
                select(Role)
                .join(UserRoleLink)
                .where(UserRoleLink.user_id == uid)
            )
        ).scalars().all()
    return rows


@router.delete("/{uid}")
async def delete_user(
    uid: str, request: Request, _=Depends(require_permission("users:manage"))
):
    """Delete a user with its role links and API keys.

    Requires the ``users:manage`` permission. Deleting a missing user is a no-op.

    Returns:
        ``{"ok": True}``.
    """
    async with request.app.state.session_factory() as s:
        user = (await s.execute(select(User).where(User.id == uid))).scalars().first()
        if user is not None:
            links = (
                await s.execute(
                    select(UserRoleLink).where(UserRoleLink.user_id == uid)
                )
            ).scalars().all()
            for link in links:
                await s.delete(link)
            keys = (
                await s.execute(select(ApiKey).where(ApiKey.user_id == uid))
            ).scalars().all()
            for key in keys:
                await s.delete(key)
            await s.delete(user)
            await s.commit()
            logger.info("user deleted id={}", uid)
    return {"ok": True}
