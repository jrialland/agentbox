"""ACP (Agent Client Protocol) adapter for Agentbox.

Runs Agentbox as an ACP v1 agent over stdio (``agentbox-acp --agent <name>``),
driving the harness and adapting the core session storage.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import os
import pathlib
import re
import uuid
from dataclasses import dataclass, field
from typing import cast

import acp
from acp import PROTOCOL_VERSION, run_agent
from acp import schema as s
from loguru import logger
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import (
    BinaryContent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
)
from pydantic_ai.models import Model as PydanticModel
from sqlmodel import select

from agentbox_api.acp_client_tools import (
    AcpClientCapabilities,
    AcpClientTools,
    install_acp_client_tools,
)
from agentbox_api.config import Settings
from agentbox_api.dev_seed import seed_admin
from agentbox_api.logging import configure_logging
from agentbox_api.lsp_runtime import lsp_reminders
from agentbox_api.media import MediaStore
from agentbox_api.runtime import (
    compaction_config_from_settings,
    context_editing_config_from_settings,
    delete_session_data,
    resolve_agent_runtime,
    web_config_from_settings,
)
from agentbox_api.skills import prepare_agent
from agentbox_harness.events import EventBus
from agentbox_harness.harness import Harness
from agentbox_harness.lsp.manager import configure_lsp
from agentbox_harness.run import Run
from agentbox_harness.session import Session, Turn
from agentbox_harness.spec import DEFAULT_MODES, AgentSpec, McpToolBinding
from agentbox_harness.tools.registry import ToolRegistry
from agentbox_harness.tools.terminal import get_job_manager
from agentbox_harness.usage import context_tokens_from_usage
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.repos.message_log import DatabaseMessageLogStore
from agentbox_models.repos.project_roots import load_extra_roots
from agentbox_models.tables.auth import User
from agentbox_models.tables.core import (
    Project,
    SessionRow,
    TurnRow,
)


def prompt_parts(blocks) -> list:
    """Convert ACP ``ContentBlock``s to a ``prompt_override`` list (str / BinaryContent)."""
    parts: list = []
    for block in blocks:
        kind = getattr(block, "type", None)
        if kind == "text":
            parts.append(block.text)
        elif kind == "resource_link":
            mime = f" ({block.mime_type})" if getattr(block, "mime_type", None) else ""
            parts.append(f"[resource: {block.name} {block.uri}{mime}]")
        elif kind in ("image", "audio"):
            parts.append(
                BinaryContent(data=base64.b64decode(block.data), media_type=block.mime_type)
            )
        elif kind == "resource":
            resource = block.resource
            text = getattr(resource, "text", None)
            blob = getattr(resource, "blob", None)
            if text is not None:
                parts.append(f"[resource {resource.uri}]\n{text}")
            elif blob is not None:
                media = (
                    getattr(resource, "mime_type", None) or "application/octet-stream"
                )
                parts.append(
                    BinaryContent(data=base64.b64decode(blob), media_type=media)
                )
            else:
                raise ValueError("invalid embedded resource")
        else:
            raise ValueError(f"unsupported content block: {kind}")
    return parts


def update_for_event(event):
    """Map a Pydantic AI stream event to an ACP ``session/update`` payload (or None)."""
    if isinstance(event, PartStartEvent):
        part = event.part
        if isinstance(part, TextPart) and part.content:
            return s.AgentMessageChunk(content=s.TextContentBlock(text=part.content))
        if isinstance(part, ThinkingPart) and part.content:
            return s.AgentThoughtChunk(content=s.TextContentBlock(text=part.content))
        return None
    if isinstance(event, PartDeltaEvent):
        delta = event.delta
        text = getattr(delta, "content_delta", None)
        if isinstance(delta, TextPartDelta) and text:
            return s.AgentMessageChunk(content=s.TextContentBlock(text=text))
        if isinstance(delta, ThinkingPartDelta) and text:
            return s.AgentThoughtChunk(content=s.TextContentBlock(text=text))
        return None
    if isinstance(event, FunctionToolCallEvent):
        part = event.part
        return s.ToolCallStart(
            tool_call_id=part.tool_call_id,
            title=part.tool_name,
            name=part.tool_name,
            kind="other",
            status="pending",
        )
    if isinstance(event, FunctionToolResultEvent):
        part = event.part
        text = event.content if event.content is not None else str(part.content)
        return s.ToolCallProgress(
            tool_call_id=part.tool_call_id,
            status="completed",
            content=[s.ContentToolCallContent(content=s.TextContentBlock(text=text))],
        )
    return None


@dataclass
class AcpSession:
    """Live state for one ACP session served by :class:`AgentboxAcpAgent`.

    This is an agent session: it binds a persisted session row to the resolved
    agent spec, model, tool registry, and active mode, plus any client tools and
    the currently running harness run.
    """

    session_id: str
    project_root: str
    project_id: str
    agent_id: str
    spec: AgentSpec
    model: PydanticModel
    registry: ToolRegistry
    mode: str
    subagent_session_runner: object | None = None
    run: Run | None = None
    extra_roots: list[str] = field(default_factory=list)
    plugin_roots: list[str] = field(default_factory=list)
    plugin_hooks: AbstractCapability | None = None
    client_tools: AcpClientTools | None = None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _default_mode(spec) -> str:
    names = [m.name for m in spec.mode_definitions] or ["ask", "agent"]
    return "agent" if "agent" in names else names[0]


def _modes(spec, current: str) -> s.SessionModeState:
    modes = spec.mode_definitions or list(DEFAULT_MODES)
    return s.SessionModeState(
        current_mode_id=current,
        available_modes=[s.SessionMode(id=m.name, name=m.name.capitalize()) for m in modes],
    )


async def _latest_leaf(factory, session_id: str):
    async with factory() as db:
        turns = (
            await db.execute(
                select(TurnRow).where(TurnRow.session_id == session_id)
            )
        ).scalars().all()
    turns = sorted(turns, key=lambda t: t.created_at)
    if not turns:
        return None
    parents = {t.parent_id for t in turns if t.parent_id}
    leaves = [t for t in turns if t.id not in parents]
    return leaves[-1].id if leaves else None


class AgentboxAcpAgent:
    """ACP v1 agent implementation that runs Agentbox harness sessions.

    The ACP stdio server dispatches protocol requests to the public methods here
    on behalf of external ACP clients; they are not called directly by internal
    Agentbox code. Sessions created or restored here are persisted as normal
    agent sessions and can be listed, loaded, resumed, closed, and deleted.
    """

    def __init__(self, agent_name: str, factory, settings):
        self._agent_name = agent_name
        self._factory = factory
        self._settings = settings
        self._media_store = MediaStore(settings.media_dir) if settings is not None else None
        self._client: acp.Client | None = None
        self._sessions: dict[str, AcpSession] = {}
        self._client_capabilities = AcpClientCapabilities()
        from agentbox_harness.tools.mcp_session import get_mcp_session_manager

        self.mcp_manager = get_mcp_session_manager()

    def on_connect(self, conn: acp.Client) -> None:
        """Record the connected ACP client used for callbacks.

        Args:
            conn: Client connection provided by the ACP runtime on connect.
        """
        self._client = conn

    @property
    def client_capabilities(self) -> AcpClientCapabilities:
        """Capabilities the connected client advertised during ``initialize``."""
        return self._client_capabilities

    async def initialize(
        self, protocol_version, client_capabilities=None, client_info=None, **kwargs
    ):
        """Negotiate the protocol version and advertise agent capabilities.

        Called by an external ACP client at the start of the connection. The
        client's capabilities are recorded for later client-tool installation,
        and this agent advertises session loading, image/audio/embedded-context
        prompt support, and list, delete, resume, and close session support.

        Args:
            protocol_version: Protocol version requested by the client.
            client_capabilities: Capabilities advertised by the client.
            client_info: Client implementation metadata (unused).
            **kwargs: Additional protocol fields accepted for compatibility.

        Returns:
            The initialize response echoing the negotiated protocol version.
        """
        self._client_capabilities = AcpClientCapabilities.from_sdk(
            client_capabilities
        )
        return s.InitializeResponse(
            protocol_version=PROTOCOL_VERSION,
            agent_capabilities=s.AgentCapabilities(
                load_session=True,
                prompt_capabilities=s.PromptCapabilities(
                    image=True, audio=True, embedded_context=True
                ),
                session_capabilities=s.SessionCapabilities(
                    list=s.SessionListCapabilities(),
                    delete=s.SessionDeleteCapabilities(),
                    resume=s.SessionResumeCapabilities(),
                    close=s.SessionCloseCapabilities(),
                ),
            ),
            auth_methods=[],
            agent_info=s.Implementation(name="agentbox", version="0.1.0"),
        )

    async def new_session(
        self, cwd, additional_directories=None, mcp_servers=None, **kwargs
    ):
        """Create and persist a new ACP session for the configured agent.

        Called by an external ACP client. The working directory becomes the
        project root, extra roots and per-session MCP servers are applied, and
        client tools are installed when the client is connected.

        Args:
            cwd: Working directory the session is rooted at.
            additional_directories: Extra directories the client allows access
                to (accepted for protocol compatibility; extra roots come from
                the project configuration).
            mcp_servers: Session-scoped MCP servers supplied by the client.
            **kwargs: Additional protocol fields accepted for compatibility.

        Returns:
            The new session response including the session id and modes.
        """
        session_id = uuid.uuid4().hex
        async with self._factory() as db:
            project = (
                await db.execute(select(Project).where(Project.path == cwd))
            ).scalars().first()
            extra_roots = (
                await load_extra_roots(db, project.id) if project is not None else []
            )
        prepared = await prepare_agent(
            self._factory,
            self._agent_name,
            cwd,
            self._settings.skills_user_dir,
            session_id=session_id,
            session_mode="agent",
            media_max_dimension=self._settings.media_max_dimension,
            media_max_bytes=self._settings.media_max_bytes,
            web_config=web_config_from_settings(self._settings),
            extra_roots=extra_roots or None,
            compaction=compaction_config_from_settings(self._settings),
            context_editing=context_editing_config_from_settings(
                self._settings
            ),
            project_id=project.id if project is not None else None,
            plugins_user_dir=self._settings.plugins_user_dir,
            plugins_data_dir=self._settings.plugins_data_dir,
        )
        runtime = prepared.runtime
        owner = runtime.created_by or await self._admin_id()
        async with self._factory() as db:
            if project is None:
                project = Project(
                    id=uuid.uuid4().hex,
                    name=pathlib.Path(cwd).name or cwd,
                    path=cwd,
                    owner_id=owner,
                )
                db.add(project)
            db.add(
                SessionRow(
                    id=session_id, project_id=project.id, agent_id=runtime.agent_id
                )
            )
            await db.commit()
            project_id = project.id
        client_tools = None
        if self._client is not None:
            # Client tools are only installed for capabilities negotiated during
            # initialize, falling back to native tools otherwise.
            client_tools = AcpClientTools(
                client=self._client,
                session_id=session_id,
                project_root=cwd,
                extra_roots=extra_roots,
                capabilities=self._client_capabilities,
            )
            install_acp_client_tools(
                prepared.registry, prepared.spec, client_tools
            )
        spec = self._with_servers(prepared.spec, mcp_servers)
        mode = _default_mode(spec)
        self._sessions[session_id] = AcpSession(
            session_id, cwd, project_id, runtime.agent_id, spec, runtime.model,
            prepared.registry, mode, prepared.subagent_session_runner,
            extra_roots=extra_roots,
            plugin_roots=[str(path) for path in prepared.plugin_roots],
            plugin_hooks=prepared.plugin_hooks,
            client_tools=client_tools,
        )
        logger.info("acp session new agent={} session={}", self._agent_name, session_id)
        return s.NewSessionResponse(session_id=session_id, modes=_modes(spec, mode))

    async def prompt(self, session_id, prompt, **kwargs):
        """Run one user prompt for a session and stream updates to the client.

        Called by an external ACP client. Prompt content blocks are converted to
        the harness prompt override, harness events are translated into ACP
        ``session/update`` notifications, and the assistant turn is persisted on
        success.

        Args:
            session_id: Session to run the prompt in.
            prompt: ACP content blocks forming the user turn.
            **kwargs: Additional protocol fields accepted for compatibility.

        Returns:
            The prompt response reporting the stop reason.

        Raises:
            acp.RequestError: If the session id is unknown.
            RuntimeError: If no ACP client is connected.
        """
        sess = self._sessions.get(session_id)
        if sess is None:
            raise acp.RequestError(-32002, "unknown session")
        client = self._client
        if client is None:
            raise RuntimeError("ACP client not connected")
        logger.info("acp run start session={}", session_id)
        parts = prompt_parts(prompt)
        text = "".join(p for p in parts if isinstance(p, str))
        store = DatabaseMessageLogStore(self._factory, session_id)
        session = Session(
            session_id=session_id,
            project_root=sess.project_root,
            agent_spec=sess.spec,
            store=store,
            head_id=await _latest_leaf(self._factory, session_id),
            mode_name=sess.mode,
            extra_roots=sess.extra_roots,
            plugin_roots=sess.plugin_roots,
        )
        harness = Harness(
            registry=sess.registry,
            model=sess.model,
            store_factory=lambda: DatabaseMessageLogStore(self._factory, session_id),
            compaction=compaction_config_from_settings(self._settings),
            subagent_session_runner=sess.subagent_session_runner,
            reminders=lsp_reminders(),
            context_editing=context_editing_config_from_settings(
                self._settings
            ),
            plugin_hooks=sess.plugin_hooks,
        )
        warnings = (await harness.prepare_mcp(session)).warnings
        for warning in warnings:
            logger.warning(
                "acp mcp server unavailable session={} server={} error={}",
                session_id,
                warning.server_id,
                warning.message,
            )
        bus = EventBus()
        sub = bus.subscribe()
        run = await harness.run(session, text, bus, prompt_override=parts)
        sess.run = run

        async def finish():
            await run.await_outcome()
            bus.close()

        closer = asyncio.create_task(finish())
        try:
            async for event in sub.stream():
                update = update_for_event(event.event)
                if update is not None:
                    # Each harness stream event becomes one ACP session update;
                    # events with no ACP mapping are dropped.
                    await client.session_update(session_id=session_id, update=update)
        finally:
            # Stop the background closer before awaiting the outcome so the
            # session object is not cleared while updates are still streaming.
            closer.cancel()
        outcome = await run.await_outcome()
        sess.run = None
        if outcome.status == "success":
            result = await run.await_result()
            context_tokens = context_tokens_from_usage(result.response.usage)
            turn = Turn(
                id=uuid.uuid4().hex,
                role="assistant",
                content=str(result.output),
                parent_id=session.head_id,
                context_tokens=context_tokens,
            )
            await session.append(turn, parent_id=session.head_id)
            return s.PromptResponse(stop_reason="end_turn")
        if outcome.status == "cancelled":
            return s.PromptResponse(stop_reason="cancelled")
        await client.session_update(
            session_id=session_id,
            update=s.AgentMessageChunk(
                content=s.TextContentBlock(text=f"[error] {outcome.message}")
            ),
        )
        return s.PromptResponse(stop_reason="end_turn")

    async def cancel(self, session_id, **kwargs):
        """Cancel the run currently executing for a session.

        Called by an external ACP client; a no-op when the session has no active
        run.

        Args:
            session_id: Session whose active run should be cancelled.
            **kwargs: Additional protocol fields accepted for compatibility.
        """
        sess = self._sessions.get(session_id)
        if sess is not None and sess.run is not None:
            sess.run.cancel()
        logger.info("acp cancel session={}", session_id)

    async def set_session_mode(self, session_id, mode_id, **kwargs):
        """Switch the active mode for a session.

        Args:
            session_id: Session whose mode changes.
            mode_id: Mode identifier selected by the client.
            **kwargs: Additional protocol fields accepted for compatibility.

        Returns:
            The set-mode response.

        Raises:
            acp.RequestError: If the session id is unknown.
        """
        sess = self._sessions.get(session_id)
        if sess is None:
            raise acp.RequestError(-32002, "unknown session")
        sess.mode = mode_id
        return s.SetSessionModeResponse()

    async def list_sessions(self, cwd=None, cursor=None, **kwargs):
        """List persisted sessions belonging to the configured agent.

        Args:
            cwd: When set, only sessions whose project path matches are listed.
            cursor: Pagination cursor (accepted for protocol compatibility).
            **kwargs: Additional protocol fields accepted for compatibility.

        Returns:
            The list response with session summaries.
        """
        runtime = await resolve_agent_runtime(self._factory, self._agent_name)
        async with self._factory() as db:
            rows = (
                await db.execute(
                    select(SessionRow).where(SessionRow.agent_id == runtime.agent_id)
                )
            ).scalars().all()
            infos = []
            for row in rows:
                project = (
                    await db.execute(
                        select(Project).where(Project.id == row.project_id)
                    )
                ).scalars().first()
                if project is None or (cwd is not None and project.path != cwd):
                    continue
                turns = (
                    await db.execute(
                        select(TurnRow)
                        .where(TurnRow.session_id == row.id)
                    )
                ).scalars().all()
                turns = sorted(turns, key=lambda t: t.created_at)
                title = next((t.content[:80] for t in turns if t.role == "user"), None)
                updated = turns[-1].created_at.isoformat() if turns else None
                infos.append(
                    s.SessionInfo(
                        session_id=row.id,
                        cwd=project.path,
                        title=title,
                        updated_at=updated,
                    )
                )
        return s.ListSessionsResponse(sessions=infos)

    async def load_session(
        self, cwd, session_id, mcp_servers=None, additional_directories=None, **kwargs
    ):
        """Restore a persisted session and replay its turns to the client.

        Called by an external ACP client. The session is restored (or reused),
        then each stored user and assistant turn is replayed as a
        ``session/update`` so the client can rebuild the transcript. Summary
        turns are skipped.

        Args:
            cwd: Working directory requested by the client.
            session_id: Session to load.
            mcp_servers: Session-scoped MCP servers supplied by the client.
            additional_directories: Extra client-approved directories (accepted
                for protocol compatibility).
            **kwargs: Additional protocol fields accepted for compatibility.

        Returns:
            The load response including the available modes.

        Raises:
            acp.RequestError: If the session id is unknown or belongs to another
                agent configuration.
            RuntimeError: If no ACP client is connected.
        """
        sess = await self._restore(session_id, mcp_servers)
        client = self._client
        if client is None:
            raise RuntimeError("ACP client not connected")
        async with self._factory() as db:
            turns = (
                await db.execute(
                    select(TurnRow).where(TurnRow.session_id == session_id)
                )
            ).scalars().all()
        turns = sorted(turns, key=lambda t: t.created_at)
        for turn in turns:
            if turn.role == "summary":
                continue
            block = s.TextContentBlock(text=turn.content)
            update = (
                s.UserMessageChunk(content=block)
                if turn.role == "user"
                else s.AgentMessageChunk(content=block)
            )
            await client.session_update(session_id=session_id, update=update)
        return s.LoadSessionResponse(modes=_modes(sess.spec, sess.mode))

    async def resume_session(
        self, session_id, cwd, additional_directories=None, mcp_servers=None, **kwargs
    ):
        """Restore a session without replaying its transcript.

        Args:
            session_id: Session to resume.
            cwd: Working directory requested by the client.
            additional_directories: Extra client-approved directories (accepted
                for protocol compatibility).
            mcp_servers: Session-scoped MCP servers supplied by the client.
            **kwargs: Additional protocol fields accepted for compatibility.

        Returns:
            The resume response including the available modes.

        Raises:
            acp.RequestError: If the session id is unknown or belongs to another
                agent configuration.
        """
        sess = await self._restore(session_id, mcp_servers)
        return s.ResumeSessionResponse(modes=_modes(sess.spec, sess.mode))

    async def delete_session(self, session_id, **kwargs):
        """Delete a session and its persisted data.

        Called by an external ACP client. Client terminal resources are released
        before the session rows and media are removed.

        Args:
            session_id: Session to delete.
            **kwargs: Additional protocol fields accepted for compatibility.

        Returns:
            The delete response.
        """
        sess = self._sessions.pop(session_id, None)
        if sess is not None and sess.client_tools is not None:
            await sess.client_tools.close()
        await delete_session_data(self._factory, session_id, self._media_store)
        return s.DeleteSessionResponse()

    async def close_session(self, session_id, **kwargs):
        """Close a live session and tear down its background resources.

        Called by an external ACP client. MCP sessions, terminal jobs, and
        subagent sessions are stopped before the session is dropped from the
        in-memory map and its run is cancelled.

        Args:
            session_id: Session to close.
            **kwargs: Additional protocol fields accepted for compatibility.

        Returns:
            The close response.
        """
        from agentbox_api.subagent_sessions import cancel_subagent_sessions

        # Tear down owned resources first, then drop the session and cancel any
        # still-running harness run so nothing keeps emitting updates.
        await self.mcp_manager.close_session(session_id)
        await get_job_manager().kill_session(session_id)
        await cancel_subagent_sessions(self._factory, session_id)
        sess = self._sessions.pop(session_id, None)
        if sess is not None and sess.client_tools is not None:
            await sess.client_tools.close()
        if sess is not None and sess.run is not None:
            sess.run.cancel()
        return s.CloseSessionResponse()

    async def _restore(self, session_id: str, mcp_servers) -> AcpSession:
        async with self._factory() as db:
            row = (
                await db.execute(select(SessionRow).where(SessionRow.id == session_id))
            ).scalars().first()
            if row is None:
                raise acp.RequestError(-32002, "unknown session")
            project = (
                await db.execute(select(Project).where(Project.id == row.project_id))
            ).scalars().first()
            extra_roots = (
                await load_extra_roots(db, project.id) if project is not None else []
            )
        prepared = await prepare_agent(
            self._factory,
            self._agent_name,
            project.path,
            self._settings.skills_user_dir,
            session_id=session_id,
            session_mode="agent",
            media_max_dimension=self._settings.media_max_dimension,
            media_max_bytes=self._settings.media_max_bytes,
            web_config=web_config_from_settings(self._settings),
            extra_roots=extra_roots,
            compaction=compaction_config_from_settings(self._settings),
            context_editing=context_editing_config_from_settings(
                self._settings
            ),
            project_id=project.id if project is not None else None,
            plugins_user_dir=self._settings.plugins_user_dir,
            plugins_data_dir=self._settings.plugins_data_dir,
        )
        if row.agent_id != prepared.runtime.agent_id:
            raise acp.RequestError(-32002, "unknown session")
        old = self._sessions.get(session_id)
        if old is not None and old.client_tools is not None:
            await old.client_tools.close()
        client_tools = None
        if self._client is not None:
            client_tools = AcpClientTools(
                client=self._client,
                session_id=session_id,
                project_root=project.path,
                extra_roots=extra_roots,
                capabilities=self._client_capabilities,
            )
            install_acp_client_tools(
                prepared.registry, prepared.spec, client_tools
            )
        spec = self._with_servers(prepared.spec, mcp_servers)
        sess = AcpSession(
            session_id,
            project.path,
            project.id,
            prepared.runtime.agent_id,
            spec,
            prepared.runtime.model,
            prepared.registry,
            _default_mode(spec),
            prepared.subagent_session_runner,
            extra_roots=extra_roots,
            plugin_roots=[str(path) for path in prepared.plugin_roots],
            plugin_hooks=prepared.plugin_hooks,
            client_tools=client_tools,
        )
        self._sessions[session_id] = sess
        return sess

    async def _admin_id(self) -> str:
        async with self._factory() as db:
            user = (
                await db.execute(select(User).where(User.username == "admin"))
            ).scalars().first()
        if user is None:
            raise RuntimeError("no admin user to own ACP projects")
        return user.id

    def _with_servers(self, spec, mcp_servers):
        extra = [
            McpToolBinding(
                id=_slug(server.name) or f"acp-{i}",
                command=server.command,
                args=list(server.args),
                env={e.name: e.value for e in server.env},
            )
            for i, server in enumerate(mcp_servers or [])
        ]
        if not extra:
            return spec
        return spec.model_copy(
            update={"tool_bindings": [*spec.tool_bindings, *extra]}
        )


async def _serve(agent_name: str) -> None:
    secret = os.environ.get("JWT_SECRET") or "agentbox-acp-local-development-secret"
    settings = Settings(jwt_secret=secret)
    configure_logging(settings)
    configure_lsp(settings)
    from agentbox_harness.tools.mcp_session import get_mcp_session_manager

    get_mcp_session_manager().start_timeout = settings.mcp_start_timeout_seconds
    engine, factory = create_engine_and_sessionmaker(settings.database_url)
    await init_db(engine)
    await seed_admin(factory)
    agent = cast(acp.Agent, AgentboxAcpAgent(agent_name, factory, settings))
    await run_agent(agent)


def main() -> None:
    """Run the ACP stdio server for the agent named by ``--agent``."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True)
    args = parser.parse_args()
    asyncio.run(_serve(args.agent))


if __name__ == "__main__":
    main()


