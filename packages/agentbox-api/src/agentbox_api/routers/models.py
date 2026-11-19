import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_models.repos.crud import ModelRepository
from agentbox_models.tables.core import Agent, Model, Provider

router = APIRouter(prefix="/models", tags=["models"])


class ModelCreate(BaseModel):
    provider_id: str
    name: str


@router.get("", response_model=list[Model])
async def list_models_endpoint(
    request: Request, _=Depends(require_permission("providers:read"))
):
    return await ModelRepository(request.app.state.session_factory).list()


@router.post("", response_model=Model)
async def create_model(
    body: ModelCreate,
    request: Request,
    _=Depends(require_permission("providers:create")),
):
    async with request.app.state.session_factory() as s:
        provider = (
            await s.execute(select(Provider).where(Provider.id == body.provider_id))
        ).scalars().first()
        if provider is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        dup = (
            await s.execute(
                select(Model).where(
                    Model.provider_id == body.provider_id, Model.name == body.name
                )
            )
        ).scalars().first()
        if dup is not None:
            raise HTTPException(status_code=409, detail="Model already exists")
        model = Model(id=uuid.uuid4().hex, provider_id=body.provider_id, name=body.name)
        s.add(model)
        await s.commit()
        await s.refresh(model)
    return model


@router.delete("/{mid}")
async def delete_model(
    mid: str, request: Request, _=Depends(require_permission("providers:create"))
):
    async with request.app.state.session_factory() as s:
        model = (
            await s.execute(select(Model).where(Model.id == mid))
        ).scalars().first()
        if model is None:
            raise HTTPException(status_code=404, detail="Not found")
        in_use = (
            await s.execute(select(Agent).where(Agent.model_id == mid))
        ).scalars().first()
        if in_use is not None:
            raise HTTPException(status_code=409, detail="Model in use")
        await s.delete(model)
        await s.commit()
    return {"ok": True}
