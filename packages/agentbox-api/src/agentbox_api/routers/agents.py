import hashlib
import json
import uuid

from a2a import types as a2a_types
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from google.protobuf import json_format
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
from agentbox_models.tables.core import Agent, AgentCard

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str
    description: str = ""
    instructions: str = ""
    model: str | None = None
    model_label: str | None = None
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
        model_binding=ModelBinding(model=body.model or "", provider=""),
        model_label=body.model_label,
    )


@router.post("", response_model=AgentSpec)
async def create_agent(
    body: AgentCreate, request: Request, _=Depends(require_permission("agents:create"))
):
    if bool(body.model) == bool(body.model_label):
        raise HTTPException(
            status_code=400,
            detail="Exactly one of model or model_label is required",
        )
    repo = AgentRepository(request.app.state.session_factory)
    try:
        spec = await repo.save(_to_spec(body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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


@router.get("/{name}/card")
async def get_agent_card(
    name: str, request: Request, _=Depends(require_permission("agents:read"))
):
    async with request.app.state.session_factory() as s:
        agent = (
            await s.execute(select(Agent).where(Agent.name == name))
        ).scalars().first()
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        row = (
            await s.execute(select(AgentCard).where(AgentCard.agent_id == agent.id))
        ).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="No agent card")
    return json.loads(row.card)


@router.put("/{name}/card")
async def set_agent_card(
    name: str,
    body: dict,
    request: Request,
    _=Depends(require_permission("agents:create")),
):
    try:
        json_format.ParseDict(body, a2a_types.AgentCard())
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid A2A agent card") from None
    async with request.app.state.session_factory() as s:
        agent = (
            await s.execute(select(Agent).where(Agent.name == name))
        ).scalars().first()
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        row = (
            await s.execute(select(AgentCard).where(AgentCard.agent_id == agent.id))
        ).scalars().first()
        if row is None:
            row = AgentCard(id=uuid.uuid4().hex, agent_id=agent.id, card=json.dumps(body))
            s.add(row)
        else:
            row.card = json.dumps(body)
            s.add(row)
        await s.commit()
    logger.info("agent card set agent={}", name)
    return body


@router.delete("/{name}/card")
async def delete_agent_card(
    name: str, request: Request, _=Depends(require_permission("agents:create"))
):
    async with request.app.state.session_factory() as s:
        agent = (
            await s.execute(select(Agent).where(Agent.name == name))
        ).scalars().first()
        if agent is not None:
            row = (
                await s.execute(
                    select(AgentCard).where(AgentCard.agent_id == agent.id)
                )
            ).scalars().first()
            if row is not None:
                await s.delete(row)
                await s.commit()
    return {"ok": True}

