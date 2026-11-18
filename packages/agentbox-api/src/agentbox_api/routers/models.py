from fastapi import APIRouter, Depends, Request

from agentbox_api.deps import require_permission
from agentbox_models.repos.crud import ModelRepository
from agentbox_models.tables.core import Model

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[Model])
async def list_models_endpoint(
    request: Request, _=Depends(require_permission("providers:read"))
):
    return await ModelRepository(request.app.state.session_factory).list()
