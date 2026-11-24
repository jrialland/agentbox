"""Model-label listing endpoints."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_models.tables.core import Label

router = APIRouter(prefix="/labels", tags=["labels"])


class LabelRead(BaseModel):
    """A model label that can be assigned to models."""

    id: str
    name: str


@router.get("", response_model=list[LabelRead])
async def list_labels(
    request: Request, _=Depends(require_permission("providers:read"))
):
    """List model labels.

    Requires the ``providers:read`` permission.

    Returns:
        All labels ordered by name.
    """
    async with request.app.state.session_factory() as s:
        rows = (await s.execute(select(Label).order_by(Label.name))).scalars().all()
    return [LabelRead(id=row.id, name=row.name) for row in rows]
