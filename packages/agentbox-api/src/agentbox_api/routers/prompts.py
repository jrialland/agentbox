from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agentbox_api.deps import require_permission
from agentbox_api.templating import preview_prompt

router = APIRouter(prefix="/prompts", tags=["prompts"])


class PreviewRequest(BaseModel):
    template: str
    context: dict[str, str] = {}


@router.post("/preview")
async def preview(
    body: PreviewRequest, _=Depends(require_permission("agents:create"))
):
    return preview_prompt(body.template, body.context)
