from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from agentbox_api.deps import require_permission
from agentbox_models.repos.crud import ProviderRepository
from agentbox_models.tables.core import Provider
from agentbox_providers.models import list_models

router = APIRouter(prefix="/providers", tags=["providers"])


class ProviderCreate(BaseModel):
    id: str
    name: str
    kind: str
    base_url: str | None = None
    api_key: str | None = None
    models_url: str | None = None


@router.post("")
async def create_provider(
    body: ProviderCreate, request: Request, _=Depends(require_permission("providers:create"))
):
    repo = ProviderRepository(request.app.state.session_factory)
    return await repo.create(Provider(**body.model_dump()))


@router.get("")
async def list_providers(request: Request, _=Depends(require_permission("providers:read"))):
    return await ProviderRepository(request.app.state.session_factory).list()


@router.get("/{pid}/models")
async def provider_models(
    pid: str, request: Request, _=Depends(require_permission("providers:list-models"))
):
    provider = await ProviderRepository(request.app.state.session_factory).get(pid)
    if provider is None:
        raise HTTPException(status_code=404, detail="Not found")
    return await list_models(provider)


@router.delete("/{pid}")
async def delete_provider(
    pid: str, request: Request, _=Depends(require_permission("providers:delete"))
):
    await ProviderRepository(request.app.state.session_factory).delete(pid)
    return {"ok": True}
