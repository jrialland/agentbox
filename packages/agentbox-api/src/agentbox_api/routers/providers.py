import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_api.routers.models import ModelRead, model_read
from agentbox_models.repos.crud import ProviderRepository
from agentbox_models.tables.core import Agent, Model, ModelLabelLink, Provider
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


class ProviderUpdate(BaseModel):
    name: str | None = None
    kind: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    models_url: str | None = None


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


@router.put("/{pid}", response_model=ProviderRead)
async def update_provider(
    pid: str,
    body: ProviderUpdate,
    request: Request,
    _=Depends(require_permission("providers:create")),
):
    async with request.app.state.session_factory() as s:
        provider = (
            await s.execute(select(Provider).where(Provider.id == pid))
        ).scalars().first()
        if provider is None:
            raise HTTPException(status_code=404, detail="Not found")
        for field in ("name", "kind", "base_url", "api_key", "models_url"):
            value = getattr(body, field)
            if value is not None:
                setattr(provider, field, value)
        s.add(provider)
        await s.commit()
        await s.refresh(provider)
    return provider


@router.post("/{pid}/models/refresh", response_model=list[ModelRead])
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
        result = [await model_read(s, row) for row in rows]
    return result


@router.delete("/{pid}")
async def delete_provider(
    pid: str, request: Request, _=Depends(require_permission("providers:delete"))
):
    async with request.app.state.session_factory() as s:
        provider = (
            await s.execute(select(Provider).where(Provider.id == pid))
        ).scalars().first()
        if provider is None:
            raise HTTPException(status_code=404, detail="Not found")
        models = (
            await s.execute(select(Model).where(Model.provider_id == pid))
        ).scalars().all()
        model_ids = [m.id for m in models]
        if model_ids:
            in_use = (
                await s.execute(
                    select(Agent).where(
                        Agent.model_id.in_(model_ids)  # ty: ignore[missing-attribute]
                    )
                )
            ).scalars().first()
            if in_use is not None:
                raise HTTPException(status_code=409, detail="Model in use")
            links = (
                await s.execute(
                    select(ModelLabelLink).where(
                        ModelLabelLink.model_id.in_(model_ids)  # ty: ignore[missing-attribute]
                    )
                )
            ).scalars().all()
            for link in links:
                await s.delete(link)
        for model in models:
            await s.delete(model)
        await s.delete(provider)
        await s.commit()
    return {"ok": True}
