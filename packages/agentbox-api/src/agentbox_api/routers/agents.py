from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from agentbox_api.deps import require_permission
from agentbox_harness.spec import (
    AgentSpec,
    McpToolBinding,
    Mode,
    ModelBinding,
    NativeToolBinding,
)
from agentbox_models.repos.agents import AgentRepository

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str
    description: str = ""
    instructions: str = ""
    model: str
    tool_bindings: list[dict] = []
    mode_definitions: list[dict] = []
    sub_agent_ids: list[str] = []


def _to_spec(body: AgentCreate) -> AgentSpec:
    bindings = []
    for b in body.tool_bindings:
        if "server_url" in b:
            bindings.append(McpToolBinding(**b))
        else:
            bindings.append(NativeToolBinding(**b))
    return AgentSpec(
        name=body.name,
        description=body.description,
        instructions=body.instructions,
        tool_bindings=bindings,
        mode_definitions=[Mode(**m) for m in body.mode_definitions],
        sub_agent_ids=body.sub_agent_ids,
        model_binding=ModelBinding(model=body.model, provider=""),
    )


@router.post("")
async def create_agent(
    body: AgentCreate, request: Request, _=Depends(require_permission("agents:create"))
):
    repo = AgentRepository(request.app.state.session_factory)
    spec = await repo.save(_to_spec(body))
    return spec.model_dump()


@router.get("")
async def list_agents(request: Request, _=Depends(require_permission("agents:read"))):
    repo = AgentRepository(request.app.state.session_factory)
    return [s.model_dump() for s in await repo.list()]


@router.get("/{name}")
async def get_agent(name: str, request: Request, _=Depends(require_permission("agents:read"))):
    repo = AgentRepository(request.app.state.session_factory)
    spec = await repo.load(name)
    if spec is None:
        raise HTTPException(status_code=404, detail="Not found")
    return spec.model_dump()


@router.delete("/{name}")
async def delete_agent(
    name: str, request: Request, _=Depends(require_permission("agents:delete"))
):
    repo = AgentRepository(request.app.state.session_factory)
    await repo.delete(name)
    return {"ok": True}
