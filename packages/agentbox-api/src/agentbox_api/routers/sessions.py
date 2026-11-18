from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from agentbox_api.deps import require_permission
from agentbox_models.repos.crud import SessionRepository
from agentbox_models.tables.core import SessionRow

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    id: str
    project_id: str
    agent_id: str


@router.post("")
async def create_session(
    body: SessionCreate, request: Request, _=Depends(require_permission("sessions:create"))
):
    return await SessionRepository(request.app.state.session_factory).create(
        SessionRow(**body.model_dump())
    )


@router.get("")
async def list_sessions(request: Request, _=Depends(require_permission("sessions:read"))):
    return await SessionRepository(request.app.state.session_factory).list()


@router.get("/{sid}")
async def get_session(sid: str, request: Request, _=Depends(require_permission("sessions:read"))):
    s = await SessionRepository(request.app.state.session_factory).get(sid)
    if s is None:
        raise HTTPException(status_code=404, detail="Not found")
    return s
