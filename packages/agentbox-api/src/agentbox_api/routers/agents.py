import hashlib
import json
import re
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
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from agentbox_api import avatars
from agentbox_api.deps import require_permission
from agentbox_api.validation import required_name
from agentbox_harness.spec import (
    AgentSpec,
    McpToolBinding,
    Mode,
    ModelBinding,
    NativeToolBinding,
)
from agentbox_harness.tools.mcp import mcp_toolset_id
from agentbox_models.repos.agents import AgentRepository
from agentbox_models.tables.core import Agent, AgentCard, MediaFile, utcnow

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str
    description: str = ""
    instructions: str = ""
    model: str | None = None
    model_label: str | None = None
    tool_bindings: list[dict] = []
    mode_definitions: list[dict] = []

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return required_name(value)


_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_mcp_item(item: dict) -> None:
    server_url = str(item.get("server_url") or "").strip()
    command = str(item.get("command") or "").strip()
    if bool(server_url) == bool(command):
        raise ValueError("Each MCP server must set exactly one of server_url or command")
    if command and not str(item.get("id") or "").strip():
        raise ValueError("Local MCP servers require a non-empty id")
    args = item.get("args") or []
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise ValueError("MCP args must be a list of strings")
    env = item.get("env") or {}
    if not isinstance(env, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in env.items()
    ):
        raise ValueError("MCP env must be a string-to-string object")
    passthrough = item.get("env_passthrough") or []
    if not isinstance(passthrough, list) or not all(
        isinstance(name, str) and _ENV_NAME.match(name) for name in passthrough
    ):
        raise ValueError(
            "MCP env_passthrough entries must be valid environment variable names"
        )


def _to_spec(body: AgentCreate) -> AgentSpec:
    bindings = []
    seen: set[str] = set()
    for b in body.tool_bindings:
        if "server_url" in b or "command" in b:
            _validate_mcp_item(b)
            binding = McpToolBinding(**b)
            server_id = mcp_toolset_id(binding)
            if server_id in seen:
                raise ValueError(f"Duplicate MCP server id: {server_id}")
            seen.add(server_id)
            bindings.append(binding)
        else:
            bindings.append(NativeToolBinding(**b))
    return AgentSpec(
        name=body.name,
        description=body.description,
        instructions=body.instructions,
        tool_bindings=bindings,
        mode_definitions=[Mode(**m) for m in body.mode_definitions],
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


@router.put("/{name}", response_model=AgentSpec)
async def update_agent(
    name: str,
    body: AgentCreate,
    request: Request,
    _=Depends(require_permission("agents:create")),
):
    if body.name != name:
        raise HTTPException(status_code=400, detail="Agent name cannot be changed")
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
    logger.info("agent updated agent={}", spec.name)
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
    factory = request.app.state.session_factory
    media_store = request.app.state.media_store
    paths: list[str] = []
    async with factory() as s:
        agent = (
            await s.execute(select(Agent).where(Agent.name == name))
        ).scalars().first()
        if agent is None:
            return {"ok": True}
        media_rows = []
        if agent.avatar_file_id:
            avatar = await s.get(MediaFile, agent.avatar_file_id)
            if avatar is not None:
                media_rows.append(avatar)
        card = (
            await s.execute(select(AgentCard).where(AgentCard.agent_id == agent.id))
        ).scalars().first()
        if card is not None and card.file_id:
            card_media = await s.get(MediaFile, card.file_id)
            if card_media is not None:
                media_rows.append(card_media)
        paths = [row.storage_path for row in media_rows]
        try:
            await s.delete(agent)
            await s.flush()
            for media in media_rows:
                await s.delete(media)
            await s.commit()
        except IntegrityError:
            await s.rollback()
            raise HTTPException(
                status_code=409, detail="Agent is still referenced"
            ) from None
    for path in paths:
        media_store.delete(path)
    logger.info("agent deleted agent={}", name)
    return {"ok": True}


@router.get("/{name}/avatar")
async def get_avatar(name: str, request: Request):
    factory = request.app.state.session_factory
    media_store = request.app.state.media_store
    async with factory() as s:
        agent = (
            await s.execute(select(Agent).where(Agent.name == name))
        ).scalars().first()
        if agent is None:
            raise HTTPException(status_code=404, detail="Not found")
        media_file = (
            await s.get(MediaFile, agent.avatar_file_id)
            if agent.avatar_file_id
            else None
        )
    if media_file is not None:
        try:
            data = media_store.read(media_file.storage_path)
        except FileNotFoundError:
            logger.warning(
                "avatar file missing agent={} path={}",
                name,
                media_file.storage_path,
            )
        else:
            etag = '"' + media_file.sha256 + '"'
            if request.headers.get("if-none-match") == etag:
                return Response(status_code=304)
            return Response(
                content=data,
                media_type=media_file.media_type,
                headers={"ETag": etag, "Cache-Control": "no-cache"},
            )
    data = avatars.generate_default_avatar(agent.id)
    etag = '"' + hashlib.sha256(data).hexdigest() + '"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    return Response(
        content=data,
        media_type="image/png",
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
    media_store = request.app.state.media_store
    stored = media_store.save(
        normalized, category="avatars", media_type="image/png", suffix=".png"
    )
    media_id = uuid.uuid4().hex
    old_path: str | None = None
    try:
        async with factory() as s:
            agent = (
                await s.execute(select(Agent).where(Agent.name == name))
            ).scalars().first()
            if agent is None:
                raise HTTPException(status_code=404, detail="Not found")
            old = (
                await s.get(MediaFile, agent.avatar_file_id)
                if agent.avatar_file_id
                else None
            )
            old_path = old.storage_path if old is not None else None
            s.add(
                MediaFile(
                    id=media_id,
                    storage_path=stored.storage_path,
                    media_type=stored.media_type,
                    size_bytes=stored.size_bytes,
                    sha256=stored.sha256,
                )
            )
            await s.flush()
            agent.avatar_file_id = media_id
            s.add(agent)
            await s.flush()
            if old is not None:
                await s.delete(old)
            await s.commit()
    except Exception:
        media_store.delete(stored.storage_path)
        raise
    if old_path is not None:
        media_store.delete(old_path)
    logger.info("avatar updated agent={}", name)
    return Response(status_code=204)


@router.delete("/{name}/avatar")
async def reset_avatar(
    name: str,
    request: Request,
    _=Depends(require_permission("agents:create")),
):
    factory = request.app.state.session_factory
    media_store = request.app.state.media_store
    old_path: str | None = None
    async with factory() as s:
        agent = (
            await s.execute(select(Agent).where(Agent.name == name))
        ).scalars().first()
        if agent is None:
            raise HTTPException(status_code=404, detail="Not found")
        old = (
            await s.get(MediaFile, agent.avatar_file_id)
            if agent.avatar_file_id
            else None
        )
        old_path = old.storage_path if old is not None else None
        agent.avatar_file_id = None
        s.add(agent)
        await s.flush()
        if old is not None:
            await s.delete(old)
        await s.commit()
    if old_path is not None:
        media_store.delete(old_path)
    logger.info("avatar reset agent={}", name)
    return Response(status_code=204)


@router.get("/{name}/card")
async def get_agent_card(
    name: str, request: Request, _=Depends(require_permission("agents:read"))
):
    media_store = request.app.state.media_store
    async with request.app.state.session_factory() as s:
        agent = (
            await s.execute(select(Agent).where(Agent.name == name))
        ).scalars().first()
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        row = (
            await s.execute(select(AgentCard).where(AgentCard.agent_id == agent.id))
        ).scalars().first()
        media = (
            await s.get(MediaFile, row.file_id)
            if row is not None and row.file_id
            else None
        )
    if row is None or media is None:
        raise HTTPException(status_code=404, detail="No agent card")
    try:
        return json.loads(media_store.read(media.storage_path))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No agent card") from None


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

    factory = request.app.state.session_factory
    media_store = request.app.state.media_store
    stored = media_store.save(
        json.dumps(body).encode(),
        category="agent-cards",
        media_type="application/json",
        suffix=".json",
    )
    media_id = uuid.uuid4().hex
    old_path: str | None = None
    try:
        async with factory() as s:
            agent = (
                await s.execute(select(Agent).where(Agent.name == name))
            ).scalars().first()
            if agent is None:
                raise HTTPException(status_code=404, detail="Agent not found")
            row = (
                await s.execute(
                    select(AgentCard).where(AgentCard.agent_id == agent.id)
                )
            ).scalars().first()
            old = (
                await s.get(MediaFile, row.file_id)
                if row is not None and row.file_id
                else None
            )
            old_path = old.storage_path if old is not None else None
            s.add(
                MediaFile(
                    id=media_id,
                    storage_path=stored.storage_path,
                    media_type=stored.media_type,
                    size_bytes=stored.size_bytes,
                    sha256=stored.sha256,
                )
            )
            await s.flush()
            if row is None:
                row = AgentCard(
                    id=uuid.uuid4().hex,
                    agent_id=agent.id,
                    file_id=media_id,
                    updated_at=utcnow(),
                )
                s.add(row)
            else:
                row.file_id = media_id
                row.updated_at = utcnow()
                s.add(row)
            await s.flush()
            if old is not None:
                await s.delete(old)
            await s.commit()
    except Exception:
        media_store.delete(stored.storage_path)
        raise
    if old_path is not None:
        media_store.delete(old_path)
    logger.info("agent card set agent={}", name)
    return body


@router.delete("/{name}/card")
async def delete_agent_card(
    name: str, request: Request, _=Depends(require_permission("agents:create"))
):
    media_store = request.app.state.media_store
    old_path: str | None = None
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
                old = (
                    await s.get(MediaFile, row.file_id)
                    if row.file_id
                    else None
                )
                old_path = old.storage_path if old is not None else None
                await s.delete(row)
                await s.flush()
                if old is not None:
                    await s.delete(old)
                await s.commit()
    if old_path is not None:
        media_store.delete(old_path)
    return {"ok": True}

