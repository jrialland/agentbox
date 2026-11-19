import asyncio
import os
import pathlib
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from loguru import logger
from pydantic import BaseModel
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_api.runtime import delete_session_data
from agentbox_api.skills import prepare_agent, render_skill
from agentbox_api.streaming import agui_response
from agentbox_harness.events import EventBus
from agentbox_harness.harness import Harness
from agentbox_harness.session import Session, Turn
from agentbox_models.repos.agents import AgentRepository
from agentbox_models.repos.crud import SessionRepository
from agentbox_models.repos.message_log import SQLiteMessageLogStore
from agentbox_models.tables.core import (
    Agent,
    Project,
    SessionAttachment,
    SessionRow,
    TurnRow,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    project_id: str
    agent_id: str


class MessageRequest(BaseModel):
    content: str
    mode: str | None = None
    skill: str | None = None
    fork: bool = False
    fork_from_turn_id: str | None = None
    attachment_ids: list[str] = []


@router.post("", response_model=SessionRow)
async def create_session(
    body: SessionCreate, request: Request, _=Depends(require_permission("sessions:create"))
):
    factory = request.app.state.session_factory
    async with factory() as s:
        agent = (
            await s.execute(select(Agent).where(Agent.name == body.agent_id))
        ).scalars().first()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    session = SessionRow(
        id=uuid.uuid4().hex, project_id=body.project_id, agent_id=agent.id
    )
    row = await SessionRepository(factory).create(session)
    logger.info("session created session={}", row.id)
    return row


@router.get("", response_model=list[SessionRow])
async def list_sessions(request: Request, _=Depends(require_permission("sessions:read"))):
    return await SessionRepository(request.app.state.session_factory).list()


class SessionDetail(BaseModel):
    id: str
    project_id: str
    agent_id: str
    agent_name: str
    head_turn_id: str | None = None
    created_at: str


@router.get("/{sid}", response_model=SessionDetail)
async def get_session(
    sid: str, request: Request, _=Depends(require_permission("sessions:read"))
):
    async with request.app.state.session_factory() as s:
        row = (
            await s.execute(select(SessionRow).where(SessionRow.id == sid))
        ).scalars().first()
        if row is None:
            raise HTTPException(status_code=404, detail="Not found")
        agent = (
            await s.execute(select(Agent).where(Agent.id == row.agent_id))
        ).scalars().first()
    return SessionDetail(
        id=row.id,
        project_id=row.project_id,
        agent_id=row.agent_id,
        agent_name=agent.name if agent is not None else "",
        head_turn_id=row.head_turn_id,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


@router.delete("/{sid}")
async def delete_session(
    sid: str, request: Request, _=Depends(require_permission("sessions:create"))
):
    factory = request.app.state.session_factory
    async with factory() as s:
        row = (
            await s.execute(select(SessionRow).where(SessionRow.id == sid))
        ).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    await delete_session_data(factory, sid)
    return {"ok": True}


class MessageRead(BaseModel):
    id: str
    role: str
    content: str
    parent_id: str | None = None
    created_at: str


@router.get("/{sid}/messages", response_model=list[MessageRead])
async def list_messages(
    sid: str, request: Request, _=Depends(require_permission("sessions:read"))
):
    async with request.app.state.session_factory() as s:
        rows = (
            await s.execute(select(TurnRow).where(TurnRow.session_id == sid))
        ).scalars().all()
    by_id = {r.id: r for r in rows}
    parent_ids = {r.parent_id for r in rows if r.parent_id}
    leaves = [r for r in rows if r.id not in parent_ids]
    if not leaves:
        return []
    leaf = max(leaves, key=lambda r: (r.created_at.isoformat() if r.created_at else ""))
    chain = []
    cur = leaf
    while cur is not None:
        chain.append(cur)
        cur = by_id.get(cur.parent_id) if cur.parent_id else None
    chain.reverse()
    return [
        MessageRead(
            id=r.id,
            role=r.role,
            content=r.content,
            parent_id=r.parent_id,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in chain
    ]


class AttachmentRead(BaseModel):
    id: str
    media_type: str
    filename: str


@router.post("/{sid}/attachments", response_model=AttachmentRead)
async def upload_attachment(
    sid: str,
    request: Request,
    file: UploadFile = File(...),
    _=Depends(require_permission("sessions:create")),
):
    data = await file.read()
    row = SessionAttachment(
        id=uuid.uuid4().hex,
        session_id=sid,
        media_type=file.content_type or "application/octet-stream",
        filename=file.filename or "file",
        data=data,
    )
    async with request.app.state.session_factory() as s:
        s.add(row)
        await s.commit()
    return AttachmentRead(id=row.id, media_type=row.media_type, filename=row.filename)


class ReadResourceBody(BaseModel):
    uri: str


class CallToolBody(BaseModel):
    name: str
    arguments: dict = {}


async def _agent_spec(request: Request, sid: str):
    factory = request.app.state.session_factory
    async with factory() as s:
        srow = (
            await s.execute(select(SessionRow).where(SessionRow.id == sid))
        ).scalars().first()
        if srow is None:
            raise HTTPException(status_code=404, detail="Session not found")
        agent = (
            await s.execute(select(Agent).where(Agent.id == srow.agent_id))
        ).scalars().first()
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
    return await AgentRepository(factory).load(agent.name)


@router.post("/{sid}/mcp/{server_id}/resources/read")
async def read_app_resource(
    sid: str,
    server_id: str,
    body: ReadResourceBody,
    request: Request,
    _=Depends(require_permission("sessions:create")),
):
    from agentbox_api import mcp_relay

    spec = await _agent_spec(request, sid)
    try:
        return await mcp_relay.read_resource_for_app(spec, server_id, body.uri)
    except KeyError:
        raise HTTPException(status_code=404, detail="MCP server not found") from None


@router.post("/{sid}/mcp/{server_id}/tools/call")
async def call_app_tool(
    sid: str,
    server_id: str,
    body: CallToolBody,
    request: Request,
    _=Depends(require_permission("sessions:create")),
):
    from agentbox_api import mcp_relay

    spec = await _agent_spec(request, sid)
    try:
        return await mcp_relay.call_tool_for_app(
            spec, server_id, body.name, body.arguments
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="MCP server not found") from None


@router.post("/{sid}/messages")
async def chat(
    sid: str,
    body: MessageRequest,
    request: Request,
    _=Depends(require_permission("sessions:create")),
):
    factory = request.app.state.session_factory
    async with factory() as s:
        srow = (
            await s.execute(select(SessionRow).where(SessionRow.id == sid))
        ).scalars().first()
        if srow is None:
            raise HTTPException(status_code=404, detail="Session not found")
        agent = (
            await s.execute(select(Agent).where(Agent.id == srow.agent_id))
        ).scalars().first()
        project = (
            await s.execute(select(Project).where(Project.id == srow.project_id))
        ).scalars().first()

    prepared = await prepare_agent(
        factory,
        agent.name,
        project.path,
        request.app.state.settings.skills_user_dir,
        media_max_dimension=request.app.state.settings.media_max_dimension,
        media_max_bytes=request.app.state.settings.media_max_bytes,
    )
    spec = prepared.spec
    resolved = prepared.runtime.model

    store = SQLiteMessageLogStore(factory, sid)
    session = Session(
        session_id=sid,
        project_root=project.path,
        agent_spec=spec,
        store=store,
        head_id=None,
        mode_name=body.mode or "agent",
    )
    if body.fork:
        session.head_id = body.fork_from_turn_id
    else:
        turns = await store.list_turns()
        if turns:
            parents = {t.parent_id for t in turns if t.parent_id}
            leaves = [t for t in turns if t.id not in parents]
            if leaves:
                session.head_id = leaves[-1].id

    binary = []
    if body.attachment_ids:
        from pydantic_ai.messages import BinaryContent

        async with factory() as s:
            arows = (
                await s.execute(
                    select(SessionAttachment).where(
                        SessionAttachment.id.in_(body.attachment_ids)  # ty: ignore[missing-attribute]
                    )
                )
            ).scalars().all()
        binary = [BinaryContent(data=a.data, media_type=a.media_type) for a in arows]

    prefix = []
    if body.skill:
        skill = next((s for s in prepared.skills if s.name == body.skill), None)
        if skill is None:
            raise HTTPException(status_code=400, detail="Unknown skill")
        prefix = [render_skill(skill)]

    prompt_override = (
        [*prefix, body.content, *binary] if (prefix or binary) else None
    )

    harness = Harness(
        registry=prepared.registry,
        model=resolved,
        store_factory=lambda: SQLiteMessageLogStore(factory, sid),
    )
    bus = EventBus()
    sub = bus.subscribe()
    logger.info("run start session={} mode={}", sid, body.mode or "agent")
    run = await harness.run(session, body.content, bus, prompt_override=prompt_override)

    async def raw_events():
        async def finish():
            outcome = await run.await_outcome()
            if outcome.status == "success":
                logger.info("run finished session={} status={}", sid, outcome.status)
            else:
                logger.warning(
                    "run not successful session={} status={}", sid, outcome.status
                )
            if outcome.status == "success":
                result = await run.await_result()
                turn = Turn(
                    id=uuid.uuid4().hex,
                    role="assistant",
                    content=str(result.output),
                    parent_id=session.head_id,
                )
                await session.append(turn, parent_id=session.head_id)
            bus.close()

        closer = asyncio.create_task(finish())
        try:
            async for re in sub.stream():
                yield re
        finally:
            closer.cancel()

    return agui_response(raw_events())


_SKIP = {
    ".git", "node_modules", ".venv", "dist", "build", "__pycache__",
    ".tox", ".mypy_cache", ".pytest_cache",
}
_MAX_FILES = 1000
_MAX_DEPTH = 8


@router.get("/{sid}/files")
async def list_session_files(
    sid: str,
    request: Request,
    q: str = "",
    _=Depends(require_permission("sessions:read")),
):
    factory = request.app.state.session_factory
    async with factory() as s:
        row = (
            await s.execute(select(SessionRow).where(SessionRow.id == sid))
        ).scalars().first()
        if row is None:
            raise HTTPException(status_code=404, detail="Session not found")
        project = (
            await s.execute(select(Project).where(Project.id == row.project_id))
        ).scalars().first()
    root = pathlib.Path(project.path).resolve()
    ql = q.lower()
    results: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = pathlib.Path(dirpath).resolve().relative_to(root)
        if len(rel_dir.parts) >= _MAX_DEPTH:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d not in _SKIP]
        for name in filenames:
            try:
                rel = (
                    pathlib.Path(dirpath, name).resolve().relative_to(root).as_posix()
                )
            except ValueError:
                continue
            if ql and ql not in rel.lower():
                continue
            results.append(rel)
            if len(results) >= _MAX_FILES:
                return {"files": sorted(results)}
    return {"files": sorted(results)}

