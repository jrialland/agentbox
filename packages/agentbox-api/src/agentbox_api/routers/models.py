"""Model inventory and model-label assignment endpoints.

Models belong to a provider and can carry labels with priorities that agent
configurations reference through ``model_label``.
"""

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
    """A label to attach to a model, with a selection priority."""

    label: str
    priority: int = 0


class ModelLabelRead(BaseModel):
    """A label attached to a model."""

    id: str
    name: str
    priority: int


class ModelCreate(BaseModel):
    """Request body for registering a model under a provider."""

    provider_id: str
    name: str
    context_window: int | None = None
    labels: list[LabelAssignment] = []


class ModelLabelsUpdate(BaseModel):
    """Request body that replaces a model's full label set."""

    labels: list[LabelAssignment] = []


class ModelRead(BaseModel):
    """A model with its provider and attached labels."""

    id: str
    provider_id: str
    name: str
    context_window: int | None = None
    labels: list[ModelLabelRead] = []


async def model_read(s, model: Model) -> ModelRead:
    """Serialize a model row and its labels using an open session.

    Args:
        s: Async database session used to read the label links.
        model: Model row to serialize.

    Returns:
        The model with its labels ordered by label name.
    """
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
        context_window=model.context_window,
        labels=[
            ModelLabelRead(id=label.id, name=label.name, priority=priority)
            for label, priority in rows
        ],
    )


async def replace_labels(
    s, model_id: str, assignments: list[LabelAssignment]
) -> None:
    """Replace a model's label links with the given assignments.

    Args:
        s: Async database session; the caller commits.
        model_id: Id of the model whose labels are replaced.
        assignments: Labels to attach, each with a priority.

    Raises:
        HTTPException: 400 if a label name is empty or too long.
    """
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
    """List all models with their labels.

    Requires the ``providers:read`` permission.

    Returns:
        Every known model across all providers.
    """
    async with request.app.state.session_factory() as s:
        models = (await s.execute(select(Model))).scalars().all()
        return [await model_read(s, model) for model in models]


@router.post("", response_model=ModelRead)
async def create_model(
    body: ModelCreate,
    request: Request,
    _=Depends(require_permission("providers:create")),
):
    """Register a model under an existing provider.

    Requires the ``providers:create`` permission.

    Returns:
        The created model, or 404 when the provider does not exist and 409 when
        the provider already has a model with that name.
    """
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
        model = Model(
            id=uuid.uuid4().hex,
            provider_id=body.provider_id,
            name=body.name,
            context_window=body.context_window,
        )
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
    """Replace a model's labels.

    Requires the ``providers:create`` permission. Label names are normalized and
    validated; invalid names return 400.

    Returns:
        The updated model, or 404 when the model does not exist.
    """
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
    """Delete a model and its label links.

    Requires the ``providers:create`` permission.

    Returns:
        ``{"ok": True}``, or 404 when missing and 409 when an agent still uses
        the model.
    """
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
