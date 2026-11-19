import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_models.repos.crud import ProviderRepository
from agentbox_models.tables.core import Model, Provider
from agentbox_providers.models import list_models

router = APIRouter(prefix="/providers", tags=["providers"])


class ProviderCreate(BaseModel):
    name: str
    kind: str
    base_url: str | None = None
    api_key: str | None = None
    models_url: str | None = None


class ProviderRead(BaseModel):
    id: str
    name: str
    kind: str
    base_url: str | None = None
    models_url: str | None = None
    is_builtin: bool = False


@router.post("", response_model=ProviderRead)
async def create_provider(
    body: ProviderCreate, request: Request, _=Depends(require_permission("providers:create"))
):
    provider = await ProviderRepository(request.app.state.session_factory).create(
        Provider(id=uuid.uuid4().hex, **body.model_dump())
    )
    logger.info("provider created provider={} kind={}", provider.id, provider.kind)
    return provider


@router.get("", response_model=list[ProviderRead])
async def list_providers(request: Request, _=Depends(require_permission("providers:read"))):
    return await ProviderRepository(request.app.state.session_factory).list()


@router.post("/{pid}/models/refresh", response_model=list[Model])
async def refresh_models(
    pid: str, request: Request, _=Depends(require_permission("providers:list-models"))
):
    factory = request.app.state.session_factory
    provider = await ProviderRepository(factory).get(pid)
    if provider is None:
        raise HTTPException(status_code=404, detail="Not found")
    names = await list_models(provider)
    logger.info("models refreshed provider={} count={}", pid, len(names))
    async with factory() as s:
        existing = (
            await s.execute(select(Model).where(Model.provider_id == pid))
        ).scalars().all()
        have = {m.name for m in existing}
        for name in names:
            if name not in have:
                s.add(Model(id=uuid.uuid4().hex, provider_id=pid, name=name))
        await s.commit()
        rows = (
            await s.execute(select(Model).where(Model.provider_id == pid))
        ).scalars().all()
    return rows


@router.delete("/{pid}")
async def delete_provider(
    pid: str, request: Request, _=Depends(require_permission("providers:delete"))
):
    await ProviderRepository(request.app.state.session_factory).delete(pid)
    return {"ok": True}
