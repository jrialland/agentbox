import asyncio
import pathlib
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_api.streaming import agui_response
from agentbox_harness.events import EventBus
from agentbox_harness.harness import Harness
from agentbox_harness.session import Session, Turn
from agentbox_harness.tools.filesystem import FilesystemToolbox
from agentbox_harness.tools.registry import ToolRegistry
from agentbox_models.repos.agents import AgentRepository
from agentbox_models.repos.crud import SessionRepository
from agentbox_models.repos.message_log import SQLiteMessageLogStore
from agentbox_models.tables.core import (
    Agent,
    Model,
    Project,
    Provider,
    SessionAttachment,
    SessionRow,
)
from agentbox_providers.resolver import resolve_model

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    project_id: str
    agent_id: str


class MessageRequest(BaseModel):
    content: str


@router.post("", response_model=SessionRow)
async def create_session(
    body: SessionCreate, request: Request, _=Depends(require_permission("sessions:create"))
):
    session = SessionRow(
        id=uuid.uuid4().hex, project_id=body.project_id, agent_id=body.agent_id
    )
    return await SessionRepository(request.app.state.session_factory).create(session)


@router.get("", response_model=list[SessionRow])
async def list_sessions(request: Request, _=Depends(require_permission("sessions:read"))):
    return await SessionRepository(request.app.state.session_factory).list()


@router.get("/{sid}", response_model=SessionRow)
async def get_session(sid: str, request: Request, _=Depends(require_permission("sessions:read"))):
    s = await SessionRepository(request.app.state.session_factory).get(sid)
    if s is None:
        raise HTTPException(status_code=404, detail="Not found")
    return s


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


def _build_registry(project_root: str) -> ToolRegistry:
    box = FilesystemToolbox(pathlib.Path(project_root))
    registry = ToolRegistry()
    registry.register_native("read_text_file", box.read_text_file, required_flags=("read",))
    registry.register_native("write_file", box.write_file, required_flags=("write",))
    registry.register_native("list_directory", box.list_directory, required_flags=("read",))
    return registry


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
        model = (
            await s.execute(select(Model).where(Model.id == agent.model_id))
        ).scalars().first()
        provider = (
            await s.execute(select(Provider).where(Provider.id == model.provider_id))
        ).scalars().first()
        project = (
            await s.execute(select(Project).where(Project.id == srow.project_id))
        ).scalars().first()

    spec = await AgentRepository(factory).load(agent.name)
    resolved = resolve_model(provider, model.name)

    store = SQLiteMessageLogStore(factory, sid)
    session = Session(
        session_id=sid,
        project_root=project.path,
        agent_spec=spec,
        store=store,
        head_id=None,
        mode_name="agent",
    )
    turns = await store.list_turns()
    if turns:
        parents = {t.parent_id for t in turns if t.parent_id}
        leaves = [t for t in turns if t.id not in parents]
        if leaves:
            session.head_id = leaves[-1].id

    harness = Harness(
        registry=_build_registry(project.path),
        model=resolved,
        store_factory=lambda: SQLiteMessageLogStore(factory, sid),
    )
    bus = EventBus()
    sub = bus.subscribe()
    run = await harness.run(session, body.content, bus)

    async def raw_events():
        async def finish():
            outcome = await run.await_outcome()
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
