import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_models.repos.model_labels import MAX_LABEL_LENGTH, canonical_label
from agentbox_models.tables.core import Agent, Label, Model, ModelLabelLink, Provider

router = APIRouter(prefix="/models", tags=["models"])


class LabelAssignment(BaseModel):
    label: str
    priority: int = 0


class ModelLabelRead(BaseModel):
    id: str
    name: str
    priority: int


class ModelCreate(BaseModel):
    provider_id: str
    name: str
    labels: list[LabelAssignment] = []


class ModelLabelsUpdate(BaseModel):
    labels: list[LabelAssignment] = []


class ModelRead(BaseModel):
    id: str
    provider_id: str
    name: str
    labels: list[ModelLabelRead] = []


async def model_read(s, model: Model) -> ModelRead:
    rows = (
        await s.execute(
            select(Label, ModelLabelLink.priority)
            .join(ModelLabelLink, ModelLabelLink.label_id == Label.id)  # ty: ignore[invalid-argument-type]
            .where(ModelLabelLink.model_id == model.id)
            .order_by(Label.name)
        )
    ).all()
    return ModelRead(
        id=model.id,
        provider_id=model.provider_id,
        name=model.name,
        labels=[
            ModelLabelRead(id=label.id, name=label.name, priority=priority)
            for label, priority in rows
        ],
    )


async def replace_labels(
    s, model_id: str, assignments: list[LabelAssignment]
) -> None:
    existing = (
        await s.execute(
            select(ModelLabelLink).where(ModelLabelLink.model_id == model_id)
        )
    ).scalars().all()
    for link in existing:
        await s.delete(link)
    wanted: dict[str, int] = {}
    for assignment in assignments:
        name = canonical_label(assignment.label)
        if not name or len(name) > MAX_LABEL_LENGTH:
            raise HTTPException(status_code=400, detail="Invalid label name")
        wanted[name] = assignment.priority
    for name, priority in wanted.items():
        label = (
            await s.execute(select(Label).where(Label.name == name))
        ).scalars().first()
        if label is None:
            label = Label(id=uuid.uuid4().hex, name=name)
            s.add(label)
            await s.flush()
        s.add(ModelLabelLink(model_id=model_id, label_id=label.id, priority=priority))


@router.get("", response_model=list[ModelRead])
async def list_models_endpoint(
    request: Request, _=Depends(require_permission("providers:read"))
):
    async with request.app.state.session_factory() as s:
        models = (await s.execute(select(Model))).scalars().all()
        return [await model_read(s, model) for model in models]


@router.post("", response_model=ModelRead)
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
        await s.flush()
        if body.labels:
            await replace_labels(s, model.id, body.labels)
        await s.commit()
        logger.info("model created provider={} name={}", model.provider_id, model.name)
        result = await model_read(s, model)
    return result


@router.put("/{mid}/labels", response_model=ModelRead)
async def set_model_labels(
    mid: str,
    body: ModelLabelsUpdate,
    request: Request,
    _=Depends(require_permission("providers:create")),
):
    async with request.app.state.session_factory() as s:
        model = (await s.execute(select(Model).where(Model.id == mid))).scalars().first()
        if model is None:
            raise HTTPException(status_code=404, detail="Not found")
        await replace_labels(s, mid, body.labels)
        await s.commit()
        result = await model_read(s, model)
    return result


@router.delete("/{mid}")
async def delete_model(
    mid: str, request: Request, _=Depends(require_permission("providers:create"))
):
    async with request.app.state.session_factory() as s:
        model = (await s.execute(select(Model).where(Model.id == mid))).scalars().first()
        if model is None:
            raise HTTPException(status_code=404, detail="Not found")
        in_use = (
            await s.execute(select(Agent).where(Agent.model_id == mid))
        ).scalars().first()
        if in_use is not None:
            raise HTTPException(status_code=409, detail="Model in use")
        links = (
            await s.execute(
                select(ModelLabelLink).where(ModelLabelLink.model_id == mid)
            )
        ).scalars().all()
        for link in links:
            await s.delete(link)
        await s.delete(model)
        await s.commit()
        logger.info("model deleted id={}", mid)
    return {"ok": True}
