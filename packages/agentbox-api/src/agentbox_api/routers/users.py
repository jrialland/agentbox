import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from agentbox_api.deps import require_permission
from agentbox_api.security import hash_password
from agentbox_models.repos.crud import UserRepository
from agentbox_models.tables.auth import User

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    username: str
    email: str
    password: str


@router.post("")
async def create_user(
    body: UserCreate, request: Request, _=Depends(require_permission("users:manage"))
):
    repo = UserRepository(request.app.state.session_factory)
    user = User(
        id=uuid.uuid4().hex,
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
    )
    await repo.create(user)
    return {"id": user.id, "username": user.username}


@router.get("")
async def list_users(request: Request, _=Depends(require_permission("users:manage"))):
    return await UserRepository(request.app.state.session_factory).list()


@router.delete("/{uid}")
async def delete_user(uid: str, request: Request, _=Depends(require_permission("users:manage"))):
    await UserRepository(request.app.state.session_factory).delete(uid)
    return {"ok": True}
