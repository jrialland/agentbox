"""Prompt-template preview endpoint."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agentbox_api.deps import require_permission
from agentbox_api.templating import preview_prompt

router = APIRouter(prefix="/prompts", tags=["prompts"])


class PreviewRequest(BaseModel):
    """Request body for previewing a prompt template.

    ``context`` overrides individual sample values; unknown keys are ignored.
    """

    template: str
    context: dict[str, str] = {}


@router.post("/preview")
async def preview(
    body: PreviewRequest, _=Depends(require_permission("agents:create"))
):
    """Render a prompt template against sample data for editor previews.

    Requires the ``agents:create`` permission. Template errors are returned in
    the response body rather than raised, so partially written templates still
    produce a usable preview.

    Returns:
        The rendered text, missing variables, any template error, the context
        used, and the known variable names.
    """
    return preview_prompt(body.template, body.context)
