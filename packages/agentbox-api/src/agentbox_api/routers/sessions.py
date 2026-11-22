import asyncio
import os
import pathlib
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from loguru import logger
from pydantic import BaseModel, field_validator
from sqlmodel import select

from agentbox_api.activity import RunActivityCollector
from agentbox_api.deps import require_permission
from agentbox_api.runtime import (
    compaction_config_from_settings,
    delete_session_data,
    web_config_from_settings,
)
from agentbox_api.skills import prepare_agent, render_skill
from agentbox_api.streaming import agui_response
from agentbox_api.templating import PromptTemplateError
from agentbox_harness.events import EventBus, RunEvent
from agentbox_harness.harness import Harness
from agentbox_harness.lsp.manager import get_lsp_manager
from agentbox_harness.session import Session, Turn
from agentbox_harness.tools.mcp_session import McpWarningEvent
from agentbox_harness.usage import context_tokens_from_usage
from agentbox_models.repos.agents import AgentRepository
from agentbox_models.repos.crud import SessionRepository
from agentbox_models.repos.message_log import DatabaseMessageLogStore
from agentbox_models.repos.project_roots import load_extra_roots
from agentbox_models.tables.core import (
    Agent,
    MediaFile,
    PlanItem,
    Project,
    SessionAttachment,
    SessionRow,
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
    retry_turn_id: str | None = None
    attachment_ids: list[str] = []


class SessionTitleUpdate(BaseModel):
    title: str

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        text = " ".join(value.split())
        if not text:
            raise ValueError("title is required")
        if len(text) > 120:
            raise ValueError("title must be 120 characters or fewer")
        return text


def derive_session_title(content: str) -> str:
    text = " ".join(content.split())
    return text if len(text) <= 60 else text[:57] + "..."


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
    factory = request.app.state.session_factory
    async with factory() as s:
        rows = (
            await s.execute(
                select(SessionRow).where(
                    SessionRow.parent_session_id.is_(None)  # ty: ignore[missing-attribute]
                )
            )
        ).scalars().all()
    return list(rows)


class SessionDetail(BaseModel):
    id: str
    project_id: str
    agent_id: str
    agent_name: str
    title: str | None = None
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
        title=row.title,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


@router.patch("/{sid}", response_model=SessionRow)
async def rename_session(
    sid: str,
    body: SessionTitleUpdate,
    request: Request,
    _=Depends(require_permission("sessions:create")),
):
    async with request.app.state.session_factory() as s:
        row = await s.get(SessionRow, sid)
        if row is None:
            raise HTTPException(status_code=404, detail="Not found")
        row.title = body.title
        s.add(row)
        await s.commit()
        await s.refresh(row)
    return row


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
    await delete_session_data(factory, sid, request.app.state.media_store)
    return {"ok": True}


class MessageRead(BaseModel):
    id: str
    role: str
    content: str
    parent_id: str | None = None
    created_at: str
    context_tokens: int | None = None
    activity: dict | None = None
    attachments: list[dict] | None = None


@router.get("/{sid}/messages", response_model=list[MessageRead])
async def list_messages(
    sid: str, request: Request, _=Depends(require_permission("sessions:read"))
):
    store = DatabaseMessageLogStore(request.app.state.session_factory, sid)
    turns = await store.list_turns()
    by_id = {turn.id: turn for turn in turns}
    parent_ids = {turn.parent_id for turn in turns if turn.parent_id}
    leaves = [turn for turn in turns if turn.id not in parent_ids]
    if not leaves:
        return []
    leaf = max(
        leaves,
        key=lambda turn: turn.created_at or datetime.min.replace(tzinfo=UTC),
    )
    chain = []
    current = leaf
    while current is not None:
        chain.append(current)
        if current.role == "summary" or current.parent_id is None:
            break
        current = by_id.get(current.parent_id)
    chain.reverse()
    return [
        MessageRead(
            id=turn.id,
            role=turn.role,
            content=turn.content,
            parent_id=turn.parent_id,
            created_at=turn.created_at.isoformat() if turn.created_at else "",
            context_tokens=turn.context_tokens,
            activity=turn.activity,
            attachments=turn.attachments,
        )
        for turn in chain
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
    media_store = request.app.state.media_store
    filename = file.filename or "file"
    media_type = file.content_type or "application/octet-stream"
    stored = media_store.save(
        data,
        category="attachments",
        media_type=media_type,
        suffix=pathlib.Path(filename).suffix[:16],
    )
    media_id = uuid.uuid4().hex
    attachment_id = uuid.uuid4().hex
    try:
        async with request.app.state.session_factory() as s:
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
            s.add(
                SessionAttachment(
                    id=attachment_id,
                    session_id=sid,
                    file_id=media_id,
                    filename=filename,
                )
            )
            await s.commit()
    except Exception:
        media_store.delete(stored.storage_path)
        raise
    return AttachmentRead(
        id=attachment_id, media_type=stored.media_type, filename=filename
    )


@router.get("/{sid}/attachments/{aid}")
async def download_attachment(
    sid: str,
    aid: str,
    request: Request,
    _=Depends(require_permission("sessions:read")),
):
    async with request.app.state.session_factory() as s:
        row = await s.get(SessionAttachment, aid)
        media = await s.get(MediaFile, row.file_id) if row is not None else None
    if row is None or row.session_id != sid or media is None:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        data = request.app.state.media_store.read(media.storage_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Not found") from None
    return Response(
        content=data,
        media_type=media.media_type,
        headers={"Content-Disposition": f'inline; filename="{row.filename}"'},
    )


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


async def _agent_spec_and_root(request: Request, sid: str):
    factory = request.app.state.session_factory
    async with factory() as s:
        srow = (
            await s.execute(select(SessionRow).where(SessionRow.id == sid))
        ).scalars().first()
        if srow is None:
            raise HTTPException(status_code=404, detail="Session not found")
        project = await s.get(Project, srow.project_id)
        extra_roots = (
            await load_extra_roots(s, project.id) if project is not None else []
        )
    spec = await _agent_spec(request, sid)
    return (
        spec,
        project.path if project is not None else "",
        extra_roots,
    )


@router.post("/{sid}/mcp/{server_id}/resources/read")
async def read_app_resource(
    sid: str,
    server_id: str,
    body: ReadResourceBody,
    request: Request,
    _=Depends(require_permission("sessions:create")),
):
    from agentbox_api import mcp_relay
    from agentbox_harness.tools.mcp_session import get_mcp_session_manager

    spec, project_root, extra_roots = await _agent_spec_and_root(request, sid)
    try:
        return await mcp_relay.read_resource_for_app(
            get_mcp_session_manager(),
            sid,
            project_root,
            spec,
            server_id,
            body.uri,
            extra_roots,
        )
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
    from agentbox_harness.tools.mcp_session import get_mcp_session_manager

    spec, project_root, extra_roots = await _agent_spec_and_root(request, sid)
    try:
        return await mcp_relay.call_tool_for_app(
            get_mcp_session_manager(),
            sid,
            project_root,
            spec,
            server_id,
            body.name,
            body.arguments,
            extra_roots,
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
        extra_roots = (
            await load_extra_roots(s, project.id) if project is not None else []
        )

    try:
        prepared = await prepare_agent(
            factory,
            agent.name,
            project.path,
            request.app.state.settings.skills_user_dir,
            user_name=getattr(request.user, "username", None),
            session_id=sid,
            session_mode=body.mode or "agent",
            media_max_dimension=request.app.state.settings.media_max_dimension,
            media_max_bytes=request.app.state.settings.media_max_bytes,
            web_config=web_config_from_settings(request.app.state.settings),
            extra_roots=extra_roots,
            compaction=compaction_config_from_settings(request.app.state.settings),
        )
    except PromptTemplateError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    spec = prepared.spec
    resolved = prepared.runtime.model

    store = DatabaseMessageLogStore(factory, sid)
    session = Session(
        session_id=sid,
        project_root=project.path,
        agent_spec=spec,
        store=store,
        head_id=None,
        mode_name=body.mode or "agent",
        extra_roots=extra_roots,
    )

    record_user_turn = True
    attachment_ids = list(body.attachment_ids)
    user_attachments: list[dict] = []

    if body.retry_turn_id:
        retry_turn = await store.get(body.retry_turn_id)
        prompt_turn = retry_turn
        if retry_turn.role == "assistant":
            if retry_turn.parent_id is None:
                raise HTTPException(status_code=400, detail="Retry turn has no parent")
            prompt_turn = await store.get(retry_turn.parent_id)
        if prompt_turn.role != "user":
            raise HTTPException(
                status_code=400, detail="Retry turn has no user parent"
            )
        session.head_id = prompt_turn.id
        body.content = prompt_turn.content
        record_user_turn = False
        user_attachments = prompt_turn.attachments or []
        attachment_ids = [item["id"] for item in user_attachments]
    elif body.fork:
        session.head_id = body.fork_from_turn_id
    else:
        turns = await store.list_turns()
        if turns:
            parents = {t.parent_id for t in turns if t.parent_id}
            leaves = [t for t in turns if t.id not in parents]
            if leaves:
                session.head_id = leaves[-1].id

    binary = []
    if attachment_ids:
        from pydantic_ai.messages import BinaryContent

        async with factory() as s:
            arows = (
                await s.execute(
                    select(SessionAttachment, MediaFile)
                    .join(MediaFile, MediaFile.id == SessionAttachment.file_id)  # ty: ignore[invalid-argument-type]
                    .where(
                        SessionAttachment.id.in_(attachment_ids)  # ty: ignore[missing-attribute]
                    )
                )
            ).all()
        media_store = request.app.state.media_store
        for attachment, media in arows:
            try:
                data = media_store.read(media.storage_path)
            except FileNotFoundError:
                raise HTTPException(
                    status_code=404, detail="Attachment file missing"
                ) from None
            binary.append(BinaryContent(data=data, media_type=media.media_type))
            user_attachments.append(
                {
                    "id": attachment.id,
                    "filename": attachment.filename,
                    "media_type": media.media_type,
                }
            )

    prefix = []
    if body.skill:
        skill = next((s for s in prepared.skills if s.name == body.skill), None)
        if skill is None:
            raise HTTPException(status_code=400, detail="Unknown skill")
        prefix = [render_skill(skill)]

    prompt_override = (
        [*prefix, body.content, *binary] if (prefix or binary) else None
    )

    if not srow.title:
        initial_title = derive_session_title(body.content)
        async with factory() as s:
            title_row = await s.get(SessionRow, sid)
            if title_row is not None and not title_row.title:
                title_row.title = initial_title
                s.add(title_row)
                await s.commit()
                srow.title = initial_title

    harness = Harness(
        registry=prepared.registry,
        model=resolved,
        store_factory=lambda: DatabaseMessageLogStore(factory, sid),
        compaction=compaction_config_from_settings(request.app.state.settings),
        subagent_session_runner=prepared.subagent_session_runner,
    )
    mcp_warnings = (await harness.prepare_mcp(session)).warnings
    bus = EventBus()
    sub = bus.subscribe()
    logger.info("run start session={} mode={}", sid, body.mode or "agent")
    run = await harness.run(
        session,
        body.content,
        bus,
        prompt_override=prompt_override,
        record_user_turn=record_user_turn,
        user_attachments=user_attachments or None,
    )
    registry = request.app.state.run_registry
    registry.register(sid, run)
    collector = RunActivityCollector()

    async def raw_events():
        for index, warning in enumerate(mcp_warnings):
            yield RunEvent(
                run_id="mcp",
                seq=-(index + 1),
                event=McpWarningEvent(
                    server=warning.server_id, message=warning.message
                ),
            )

        async def finish():
            try:
                outcome = await run.await_outcome()
                if outcome.status == "success":
                    logger.info("run finished session={} status={}", sid, outcome.status)
                else:
                    logger.warning(
                        "run not successful session={} status={}", sid, outcome.status
                    )
                content = collector.text
                context_tokens = None
                if outcome.status == "success":
                    result = await run.await_result()
                    content = str(result.output)
                    context_tokens = context_tokens_from_usage(result.response.usage)
                activity = collector.summary(
                    outcome.status,
                    (
                        {"code": outcome.code, "message": outcome.message}
                        if outcome.status == "error"
                        else None
                    ),
                )
                turn = Turn(
                    id=uuid.uuid4().hex,
                    role="assistant",
                    content=content,
                    parent_id=session.head_id,
                    context_tokens=context_tokens,
                    activity=activity,
                )
                await session.append(turn, parent_id=session.head_id)
            finally:
                registry.finish(sid)
                bus.close()

        closer = asyncio.create_task(finish())
        try:
            async for re in sub.stream():
                collector.observe(re.event)
                yield re
            outcome = await run.await_outcome()
            if outcome.status == "error":
                raise RuntimeError(outcome.message or "Agent run failed")
        finally:
            closer.cancel()
            registry.finish(sid)

    return agui_response(raw_events())


@router.post("/{sid}/messages/cancel", status_code=202)
async def cancel_message(
    sid: str,
    request: Request,
    _=Depends(require_permission("sessions:create")),
):
    if request.app.state.run_registry.cancel(sid):
        return {"status": "cancelling"}
    raise HTTPException(status_code=409, detail="No active run")


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

@router.get("/{sid}/lsp")
async def session_lsp(
    sid: str, request: Request, _=Depends(require_permission("sessions:read"))
):
    factory = request.app.state.session_factory
    async with factory() as s:
        srow = (
            await s.execute(select(SessionRow).where(SessionRow.id == sid))
        ).scalars().first()
        if srow is None:
            raise HTTPException(status_code=404, detail="Session not found")
        project = (
            await s.execute(select(Project).where(Project.id == srow.project_id))
        ).scalars().first()
    manager = get_lsp_manager()
    return {
        "detected": manager.detected_for_project(project.path),
        "active": manager.active_for_session(sid),
    }

class PlanItemRead(BaseModel):
    id: str
    position: int
    content: str
    status: str


class PlanRead(BaseModel):
    items: list[PlanItemRead] = []


@router.get("/{sid}/plan", response_model=PlanRead)
async def session_plan(
    sid: str, request: Request, _=Depends(require_permission("sessions:read"))
):
    factory = request.app.state.session_factory
    async with factory() as s:
        if await s.get(SessionRow, sid) is None:
            raise HTTPException(status_code=404, detail="Session not found")
        items = (
            await s.execute(
                select(PlanItem)
                .where(PlanItem.session_id == sid)
                .order_by(PlanItem.position)  # ty: ignore[invalid-argument-type]
            )
        ).scalars().all()
    return PlanRead(
        items=[
            PlanItemRead(
                id=item.id,
                position=item.position,
                content=item.content,
                status=item.status,
            )
            for item in items
        ]
    )

