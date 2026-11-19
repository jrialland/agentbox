import hashlib

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from loguru import logger
from pydantic import BaseModel
from sqlmodel import select

from agentbox_api import avatars
from agentbox_api.deps import require_permission
from agentbox_harness.spec import (
    AgentSpec,
    McpToolBinding,
    Mode,
    ModelBinding,
    NativeToolBinding,
)
from agentbox_models.repos.agents import AgentRepository
from agentbox_models.tables.core import Agent

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
        if "server_url" in b or "command" in b:
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


@router.post("", response_model=AgentSpec)
async def create_agent(
    body: AgentCreate, request: Request, _=Depends(require_permission("agents:create"))
):
    repo = AgentRepository(request.app.state.session_factory)
    spec = await repo.save(_to_spec(body))
    logger.info("agent created agent={}", spec.name)
    return spec


@router.get("", response_model=list[AgentSpec])
async def list_agents(request: Request, _=Depends(require_permission("agents:read"))):
    repo = AgentRepository(request.app.state.session_factory)
    return await repo.list()


@router.get("/{name}", response_model=AgentSpec)
async def get_agent(name: str, request: Request, _=Depends(require_permission("agents:read"))):
    repo = AgentRepository(request.app.state.session_factory)
    spec = await repo.load(name)
    if spec is None:
        raise HTTPException(status_code=404, detail="Not found")
    return spec


@router.delete("/{name}")
async def delete_agent(
    name: str, request: Request, _=Depends(require_permission("agents:delete"))
):
    repo = AgentRepository(request.app.state.session_factory)
    await repo.delete(name)
    logger.info("agent deleted agent={}", name)
    return {"ok": True}


@router.get("/{name}/avatar")
async def get_avatar(name: str, request: Request):
    factory = request.app.state.session_factory
    async with factory() as s:
        agent = (
            await s.execute(select(Agent).where(Agent.name == name))
        ).scalars().first()
    if agent is None:
        raise HTTPException(status_code=404, detail="Not found")
    if agent.avatar_data:
        data = agent.avatar_data
        media = agent.avatar_media_type or "image/png"
    else:
        data = avatars.generate_default_avatar(agent.id)
        media = "image/png"
    etag = '"' + hashlib.sha256(data).hexdigest() + '"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    return Response(
        content=data,
        media_type=media,
        headers={"ETag": etag, "Cache-Control": "no-cache"},
    )


@router.put("/{name}/avatar")
async def upload_avatar(
    name: str,
    request: Request,
    file: UploadFile = File(...),
    _=Depends(require_permission("agents:create")),
):
    if file.content_type not in avatars.ALLOWED_UPLOAD_TYPES:
        logger.warning("avatar upload rejected agent={} reason=type", name)
        raise HTTPException(status_code=415, detail="Unsupported image type")
    data = await file.read()
    if len(data) > avatars.MAX_UPLOAD_BYTES:
        logger.warning("avatar upload rejected agent={} reason=size", name)
        raise HTTPException(status_code=413, detail="Image too large")
    try:
        normalized = avatars.normalize_upload(data)
    except ValueError:
        raise HTTPException(status_code=415, detail="Invalid image") from None
    factory = request.app.state.session_factory
    async with factory() as s:
        agent = (
            await s.execute(select(Agent).where(Agent.name == name))
        ).scalars().first()
        if agent is None:
            raise HTTPException(status_code=404, detail="Not found")
        agent.avatar_data = normalized
        agent.avatar_media_type = "image/png"
        s.add(agent)
        await s.commit()
    logger.info("avatar updated agent={}", name)
    return Response(status_code=204)


@router.delete("/{name}/avatar")
async def reset_avatar(
    name: str,
    request: Request,
    _=Depends(require_permission("agents:create")),
):
    factory = request.app.state.session_factory
    async with factory() as s:
        agent = (
            await s.execute(select(Agent).where(Agent.name == name))
        ).scalars().first()
        if agent is None:
            raise HTTPException(status_code=404, detail="Not found")
        agent.avatar_data = None
        agent.avatar_media_type = None
        s.add(agent)
        await s.commit()
    logger.info("avatar reset agent={}", name)
    return Response(status_code=204)
