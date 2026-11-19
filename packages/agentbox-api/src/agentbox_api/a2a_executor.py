"""A2A executor: maps an A2A context to an Agentbox harness session."""

from __future__ import annotations

import asyncio
import uuid

from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from pydantic_ai.messages import PartDeltaEvent, PartStartEvent, TextPart, TextPartDelta
from sqlmodel import select

from agentbox_api.a2a_server import a2a_user
from agentbox_api.runtime import build_registry, resolve_agent_runtime
from agentbox_harness.events import EventBus
from agentbox_harness.harness import Harness
from agentbox_harness.session import Session, Turn
from agentbox_models.repos.message_log import SQLiteMessageLogStore
from agentbox_models.tables.auth import User
from agentbox_models.tables.core import Project, SessionRow, TurnRow


def _text_chunk(event):
    if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
        return event.part.content or None
    if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
        return event.delta.content_delta or None
    return None


async def _latest_leaf(factory, session_id: str):
    async with factory() as s:
        turns = (
            await s.execute(select(TurnRow).where(TurnRow.session_id == session_id))
        ).scalars().all()
    if not turns:
        return None
    parents = {t.parent_id for t in turns if t.parent_id}
    leaves = [t for t in turns if t.id not in parents]
    return leaves[-1].id if leaves else None


class AgentboxA2AExecutor(AgentExecutor):
    def __init__(self, agent_name, factory, settings):
        self._agent_name = agent_name
        self._factory = factory
        self._settings = settings
        self._runs = {}

    async def _owner(self) -> str:
        uid = a2a_user.get()
        if uid:
            return uid
        async with self._factory() as s:
            user = (
                await s.execute(select(User).where(User.username == "admin"))
            ).scalars().first()
        if user is None:
            raise RuntimeError("no user to own A2A projects")
        return user.id

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        message = context.message
        if message is None:
            raise ValueError("A2A request has no message")
        task = context.current_task or new_task_from_user_message(message)
        if context.current_task is None:
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()
        session_id = task.context_id
        runtime = await resolve_agent_runtime(self._factory, self._agent_name)
        owner = await self._owner()
        workspace = self._settings.a2a_workspace
        async with self._factory() as s:
            project = (
                await s.execute(select(Project).where(Project.path == workspace))
            ).scalars().first()
            if project is None:
                project = Project(
                    id=uuid.uuid4().hex,
                    name=workspace,
                    path=workspace,
                    owner_id=owner,
                )
                s.add(project)
            existing = (
                await s.execute(select(SessionRow).where(SessionRow.id == session_id))
            ).scalars().first()
            if existing is None:
                s.add(
                    SessionRow(
                        id=session_id, project_id=project.id, agent_id=runtime.agent_id
                    )
                )
            await s.commit()
        session = Session(
            session_id=session_id,
            project_root=workspace,
            agent_spec=runtime.spec,
            store=SQLiteMessageLogStore(self._factory, session_id),
            head_id=await _latest_leaf(self._factory, session_id),
            mode_name="agent",
        )
        harness = Harness(
            registry=build_registry(workspace),
            model=runtime.model,
            store_factory=lambda: SQLiteMessageLogStore(self._factory, session_id),
        )
        bus = EventBus()
        sub = bus.subscribe()
        run = await harness.run(session, get_message_text(message), bus)
        self._runs[session_id] = run

        async def finish():
            await run.await_outcome()
            bus.close()

        closer = asyncio.create_task(finish())
        try:
            async for event in sub.stream():
                chunk = _text_chunk(event.event)
                if chunk:
                    await updater.add_artifact(
                        parts=[new_text_part(text=chunk)],
                        append=True,
                        last_chunk=False,
                    )
        finally:
            closer.cancel()
        outcome = await run.await_outcome()
        self._runs.pop(session_id, None)
        if outcome.status == "success":
            result = await run.await_result()
            await session.append(
                Turn(
                    id=uuid.uuid4().hex,
                    role="assistant",
                    content=str(result.output),
                    parent_id=session.head_id,
                ),
                parent_id=session.head_id,
            )
            await updater.complete()
        else:
            await updater.failed(message=new_text_message(outcome.message or "error"))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        run = self._runs.get(context.context_id or "")
        if run is not None:
            run.cancel()
        updater = TaskUpdater(event_queue, context.task_id or "", context.context_id or "")
        await updater.cancel()

