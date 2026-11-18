import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from agentbox_api.deps import require_permission
from agentbox_models.repos.crud import RoleRepository
from agentbox_models.tables.auth import Role

router = APIRouter(prefix="/roles", tags=["roles"])


class RoleCreate(BaseModel):
    name: str
    description: str | None = None


@router.post("")
async def create_role(
    body: RoleCreate, request: Request, _=Depends(require_permission("roles:manage"))
):
    repo = RoleRepository(request.app.state.session_factory)
    return await repo.create(
        Role(id=uuid.uuid4().hex, name=body.name, description=body.description)
    )


@router.get("")
async def list_roles(request: Request, _=Depends(require_permission("roles:manage"))):
    return await RoleRepository(request.app.state.session_factory).list()


@router.delete("/{rid}")
async def delete_role(rid: str, request: Request, _=Depends(require_permission("roles:manage"))):
    await RoleRepository(request.app.state.session_factory).delete(rid)
    return {"ok": True}
