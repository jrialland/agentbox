"""Agent session lifecycle, messaging, and file endpoints.

A session is a live instance of an agent configuration within a project. These
routes create sessions, read and prune history, relay MCP resources and tools,
stream agent runs, and expose session files, plans, and LSP diagnostics.
"""

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
from agentbox_api.lsp_runtime import lsp_reminders
from agentbox_api.plugin_service import PluginService
from agentbox_api.runtime import (
    compaction_config_from_settings,
    context_editing_config_from_settings,
    delete_session_data,
    web_config_from_settings,
)
from agentbox_api.skills import prepare_agent, render_skill
from agentbox_api.streaming import agui_response
from agentbox_api.templating import PromptTemplateError
from agentbox_harness.events import EventBus, RunEvent
from agentbox_harness.harness import Harness
from agentbox_harness.lsp.diagnostics import get_diagnostics_service
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
    """Request body for starting a session.

    ``agent_id`` is the name of an existing agent configuration.
    """

    project_id: str
    agent_id: str


class MessageRequest(BaseModel):
    """Request body for sending a message to a session.

    ``mode`` selects an agent mode; ``skill`` prefixes a rendered skill.
    ``fork`` / ``fork_from_turn_id`` branch history, and ``retry_turn_id``
    re-runs a prior turn. ``attachment_ids`` reference uploaded attachments.
    """

    content: str
    mode: str | None = None
    skill: str | None = None
    fork: bool = False
    fork_from_turn_id: str | None = None
    retry_turn_id: str | None = None
    attachment_ids: list[str] = []


class SessionTitleUpdate(BaseModel):
    """Request body for renaming a session.

    Titles are trimmed to a single line and limited to 120 characters.
    """

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
    """Build a short session title from the first user message.

    Args:
        content: Raw user message text.

    Returns:
        A single-line title of at most 60 characters, truncated with an ellipsis
        when needed.
    """
    text = " ".join(content.split())
    return text if len(text) <= 60 else text[:57] + "..."


@router.post("", response_model=SessionRow)
async def create_session(
    body: SessionCreate, request: Request, _=Depends(require_permission("sessions:create"))
):
    """Start a session from an agent configuration in a project.

    Requires the ``sessions:create`` permission. ``agent_id`` is an agent
    configuration name.

    Returns:
        The new session row, or 404 when the agent configuration is missing.
    """
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
    """List top-level sessions.

    Requires the ``sessions:read`` permission. Subagent sessions (those with a
    parent session) are excluded.

    Returns:
        The top-level session rows.
    """
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
    """A session with its agent's display name."""

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
    """Get one session's details.

    Requires the ``sessions:read`` permission.

    Returns:
        The session detail, or 404 when it does not exist.
    """
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
    """Rename a session.

    Requires the ``sessions:create`` permission. The title is validated to be
    non-empty and at most 120 characters (422 otherwise).

    Returns:
        The updated session row, or 404 when it does not exist.
    """
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
    """Delete a session, its subagent sessions, and stored media.

    Requires the ``sessions:create`` permission.

    Returns:
        ``{"ok": True}``, or 404 when the session does not exist.
    """
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
    """A message in a session's conversation history."""

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
    """List the active conversation chain for a session.

    Requires the ``sessions:read`` permission. The chain follows the most recent
    leaf back to its root and stops at a compaction summary, so abandoned forks
    are not returned.

    Returns:
        The conversation messages in chronological order; empty for a session
        with no history.
    """
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
    """Metadata for an uploaded session attachment."""

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
    """Upload a file attachment for a session.

    Requires the ``sessions:create`` permission. The returned id can be passed in
    ``attachment_ids`` on a subsequent message.

    Returns:
        The attachment id, media type, and filename.
    """
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
    """Download a session attachment by id.

    Requires the ``sessions:read`` permission. The attachment must belong to the
    session in the path.

    Returns:
        The file bytes, or 404 when missing or owned by another session.
    """
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
    """Request body for reading an MCP resource."""

    uri: str


class CallToolBody(BaseModel):
    """Request body for calling an MCP tool."""

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
    settings = request.app.state.settings
    service = PluginService(
        factory,
        settings.plugins_user_dir,
        settings.plugins_data_dir,
    )
    plugin_roots = (
        await service.plugin_roots(project.id, project.path)
        if project is not None
        else []
    )
    spec = await _agent_spec(request, sid)
    return (
        spec,
        project.path if project is not None else "",
        extra_roots,
        project.id if project is not None else None,
        [str(path) for path in plugin_roots],
    )


@router.post("/{sid}/mcp/{server_id}/resources/read")
async def read_app_resource(
    sid: str,
    server_id: str,
    body: ReadResourceBody,
    request: Request,
    _=Depends(require_permission("sessions:create")),
):
    """Read a resource from an MCP server configured for the session.

    Requires the ``sessions:create`` permission. The server is resolved from the
    session's agent configuration and project.

    Returns:
        The MCP resource contents, or 404 when the session or MCP server is not
        found.
    """
    from agentbox_api import mcp_relay
    from agentbox_harness.tools.mcp_session import get_mcp_session_manager

    (
        spec,
        project_root,
        extra_roots,
        _project_id,
        plugin_roots,
    ) = await _agent_spec_and_root(request, sid)
    try:
        return await mcp_relay.read_resource_for_app(
            get_mcp_session_manager(),
            sid,
            project_root,
            spec,
            server_id,
            body.uri,
            [*extra_roots, *plugin_roots],
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
    """Call a tool on an MCP server configured for the session.

    Requires the ``sessions:create`` permission. The server is resolved from the
    session's agent configuration and project.

    Returns:
        The MCP tool result, or 404 when the session or MCP server is not found.
    """
    from agentbox_api import mcp_relay
    from agentbox_harness.tools.mcp_session import get_mcp_session_manager

    (
        spec,
        project_root,
        extra_roots,
        _project_id,
        plugin_roots,
    ) = await _agent_spec_and_root(request, sid)
    try:
        return await mcp_relay.call_tool_for_app(
            get_mcp_session_manager(),
            sid,
            project_root,
            spec,
            server_id,
            body.name,
            body.arguments,
            [*extra_roots, *plugin_roots],
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
    """Send a user message and stream the resulting agent run.

    Requires the ``sessions:create`` permission. The response is a streaming
    AG-UI event source that stays open until the run finishes; cancel it with
    ``POST /sessions/{sid}/messages/cancel``. ``retry_turn_id`` re-runs a prior
    turn, ``fork``/``fork_from_turn_id`` branch from earlier history, and
    ``skill`` prepends a rendered skill to the prompt.

    Returns:
        The streaming event response. Returns 404 for an unknown session or a
        missing attachment file, 422 for prompt-template errors, and 400 for
        invalid retry or skill references.
    """
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
            context_editing=context_editing_config_from_settings(
                request.app.state.settings
            ),
            project_id=project.id,
            plugins_user_dir=request.app.state.settings.plugins_user_dir,
            plugins_data_dir=request.app.state.settings.plugins_data_dir,
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
        plugin_roots=[str(path) for path in prepared.plugin_roots],
    )

    record_user_turn = True
    attachment_ids = list(body.attachment_ids)
    user_attachments: list[dict] = []

    if body.retry_turn_id:
        # Retrying replays the user turn behind the target instead of recording
        # a duplicate user message.
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
        # Forking continues from the requested turn rather than the latest leaf.
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

    # Name the session from its first user message so it is identifiable in
    # listings; later messages leave the title unchanged.
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
        reminders=lsp_reminders(),
        context_editing=context_editing_config_from_settings(
            request.app.state.settings
        ),
        plugin_hooks=prepared.plugin_hooks,
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
            # Persist the assistant turn and always release the run registry and
            # event bus, whether the run succeeded or not.
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
    """Request cancellation of a session's active run.

    Requires the ``sessions:create`` permission. Cancellation is cooperative, so
    the streaming response may emit a few more events before ending.

    Returns:
        202 with ``{"status": "cancelling"}``, or 409 when no run is active.
    """
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
    """List files in a session's project directory.

    Requires the ``sessions:read`` permission. ``q`` filters paths
    case-insensitively by substring. Traversal skips common build and cache
    directories and caps the result at 1000 paths and depth 8.

    Returns:
        ``{"files": [...]}`` of project-relative POSIX paths, or 404 when the
        session does not exist.
    """
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
    """Report LSP servers detected for a session's project.

    Requires the ``sessions:read`` permission.

    Returns:
        Detected servers, servers active for the session, and diagnostic
        snapshots, or 404 when the session does not exist.
    """
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
    service = get_diagnostics_service()
    return {
        "detected": manager.detected_for_project(project.path),
        "active": manager.active_for_session(sid),
        "snapshots": [
            {
                "path": snapshot.path,
                "stack": snapshot.stack,
                "state": snapshot.state,
                "errors": len(snapshot.errors),
                "warnings": len(snapshot.warnings),
                "updated_at": snapshot.updated_at,
            }
            for snapshot in service.snapshots_for_session(sid)
        ],
    }

class PlanItemRead(BaseModel):
    """One ordered item in a session's plan."""

    id: str
    position: int
    content: str
    status: str


class PlanRead(BaseModel):
    """A session's plan, ordered by position."""

    items: list[PlanItemRead] = []


@router.get("/{sid}/plan", response_model=PlanRead)
async def session_plan(
    sid: str, request: Request, _=Depends(require_permission("sessions:read"))
):
    """Get a session's plan items.

    Requires the ``sessions:read`` permission.

    Returns:
        The plan items ordered by position, or 404 when the session does not
        exist.
    """
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

