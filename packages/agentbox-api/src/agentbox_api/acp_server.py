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
from dataclasses import dataclass
from typing import cast

import acp
from acp import PROTOCOL_VERSION, run_agent
from acp import schema as s
from loguru import logger
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

from agentbox_api.config import Settings
from agentbox_api.dev_seed import seed_admin
from agentbox_api.logging import configure_logging
from agentbox_api.runtime import (
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
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.repos.message_log import SQLiteMessageLogStore
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
    session_id: str
    project_root: str
    project_id: str
    agent_id: str
    spec: AgentSpec
    model: PydanticModel
    registry: ToolRegistry
    mode: str
    run: Run | None = None


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
    def __init__(self, agent_name: str, factory, settings):
        self._agent_name = agent_name
        self._factory = factory
        self._settings = settings
        self._client: acp.Client | None = None
        self._sessions: dict[str, AcpSession] = {}

    def on_connect(self, conn: acp.Client) -> None:
        self._client = conn

    async def initialize(
        self, protocol_version, client_capabilities=None, client_info=None, **kwargs
    ):
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
        session_id = uuid.uuid4().hex
        async with self._factory() as db:
            project = (
                await db.execute(select(Project).where(Project.path == cwd))
            ).scalars().first()
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
            extra_roots=project.extra_roots if project is not None else None,
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
        spec = self._with_servers(prepared.spec, mcp_servers)
        mode = _default_mode(spec)
        self._sessions[session_id] = AcpSession(
            session_id, cwd, project_id, runtime.agent_id, spec, runtime.model,
            prepared.registry, mode,
        )
        logger.info("acp session new agent={} session={}", self._agent_name, session_id)
        return s.NewSessionResponse(session_id=session_id, modes=_modes(spec, mode))

    async def prompt(self, session_id, prompt, **kwargs):
        sess = self._sessions.get(session_id)
        if sess is None:
            raise acp.RequestError(-32002, "unknown session")
        client = self._client
        if client is None:
            raise RuntimeError("ACP client not connected")
        logger.info("acp run start session={}", session_id)
        parts = prompt_parts(prompt)
        text = "".join(p for p in parts if isinstance(p, str))
        store = SQLiteMessageLogStore(self._factory, session_id)
        session = Session(
            session_id=session_id,
            project_root=sess.project_root,
            agent_spec=sess.spec,
            store=store,
            head_id=await _latest_leaf(self._factory, session_id),
            mode_name=sess.mode,
        )
        harness = Harness(
            registry=sess.registry,
            model=sess.model,
            store_factory=lambda: SQLiteMessageLogStore(self._factory, session_id),
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
                    await client.session_update(session_id=session_id, update=update)
        finally:
            closer.cancel()
        outcome = await run.await_outcome()
        sess.run = None
        if outcome.status == "success":
            result = await run.await_result()
            turn = Turn(
                id=uuid.uuid4().hex,
                role="assistant",
                content=str(result.output),
                parent_id=session.head_id,
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
        sess = self._sessions.get(session_id)
        if sess is not None and sess.run is not None:
            sess.run.cancel()
        logger.info("acp cancel session={}", session_id)

    async def set_session_mode(self, session_id, mode_id, **kwargs):
        sess = self._sessions.get(session_id)
        if sess is None:
            raise acp.RequestError(-32002, "unknown session")
        sess.mode = mode_id
        return s.SetSessionModeResponse()

    async def list_sessions(self, cwd=None, cursor=None, **kwargs):
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
        sess = await self._restore(session_id, mcp_servers)
        return s.ResumeSessionResponse(modes=_modes(sess.spec, sess.mode))

    async def delete_session(self, session_id, **kwargs):
        await delete_session_data(self._factory, session_id)
        self._sessions.pop(session_id, None)
        return s.DeleteSessionResponse()

    async def close_session(self, session_id, **kwargs):
        await get_job_manager().kill_session(session_id)
        sess = self._sessions.pop(session_id, None)
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
            extra_roots=project.extra_roots,
        )
        if row.agent_id != prepared.runtime.agent_id:
            raise acp.RequestError(-32002, "unknown session")
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
    engine, factory = create_engine_and_sessionmaker(settings.database_url)
    await init_db(engine)
    await seed_admin(factory)
    agent = cast(acp.Agent, AgentboxAcpAgent(agent_name, factory, settings))
    await run_agent(agent)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True)
    args = parser.parse_args()
    asyncio.run(_serve(args.agent))


if __name__ == "__main__":
    main()


