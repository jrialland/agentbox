from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

from sqlmodel import select

from agentbox_api.skills import prepare_agent
from agentbox_harness.compaction import CompactionConfig
from agentbox_harness.events import EventBus
from agentbox_harness.harness import Harness
from agentbox_harness.run import Run
from agentbox_harness.session import Session, Turn
from agentbox_harness.spec import AgentSpec
from agentbox_harness.tools.web import WebToolConfig
from agentbox_harness.usage import context_tokens_from_usage
from agentbox_models.repos.message_log import SQLiteMessageLogStore
from agentbox_models.tables.core import Agent, SessionRow, TurnRow

MAX_SUB_SESSIONS = 5
MAX_SUB_SESSION_DEPTH = 3

_active: dict[str, tuple[asyncio.Task, Run]] = {}


@dataclass(frozen=True)
class SubSessionContext:
    factory: Any
    project_root: str
    skills_user_dir: str
    extra_roots: list[str]
    web_config: WebToolConfig | None
    compaction: CompactionConfig
    media_max_dimension: int
    media_max_bytes: int
    depth: int


async def _set_status(
    factory,
    child_id: str,
    status: str,
    error: str | None = None,
    output: str | None = None,
) -> None:
    async with factory() as s:
        row = await s.get(SessionRow, child_id)
        if row is not None:
            row.sub_session_status = status
            row.sub_session_error = error
            if output is not None:
                row.sub_session_output = output
            s.add(row)
            await s.commit()


async def _first_user_text(factory, child_id: str) -> str:
    async with factory() as s:
        row = (
            await s.execute(
                select(TurnRow)
                .where(TurnRow.session_id == child_id, TurnRow.role == "user")
                .order_by(TurnRow.created_at)  # ty: ignore[invalid-argument-type]
            )
        ).scalars().first()
    return row.content if row else ""


async def _latest_assistant_text(factory, child_id: str) -> str:
    async with factory() as s:
        row = (
            await s.execute(
                select(TurnRow)
                .where(TurnRow.session_id == child_id, TurnRow.role == "assistant")
                .order_by(TurnRow.created_at.desc())  # ty: ignore[missing-attribute]
            )
        ).scalars().first()
    return row.content if row else ""


async def _agent_name(factory, agent_id: str) -> str:
    async with factory() as s:
        row = await s.get(Agent, agent_id)
    return row.name if row else agent_id


class ApiSubSessionRunner:
    def __init__(self, context: SubSessionContext):
        self._context = context

    async def start(
        self,
        parent_session_id: str,
        parent_spec: AgentSpec,
        agent_name: str,
        task: str,
        wait: bool,
    ) -> str:
        if agent_name not in set(parent_spec.sub_agent_ids):
            return f"Sub-session failed: unknown agent {agent_name}."
        text = (task or "").strip()
        if not text:
            return "Sub-session failed: task must not be empty."
        if self._context.depth >= MAX_SUB_SESSION_DEPTH:
            return "Sub-session failed: maximum depth reached."

        async with self._context.factory() as s:
            parent = await s.get(SessionRow, parent_session_id)
            if parent is None:
                return "Sub-session failed: parent session not found."
            running = (
                await s.execute(
                    select(SessionRow).where(
                        SessionRow.parent_session_id == parent_session_id,
                        SessionRow.sub_session_status == "running",
                    )
                )
            ).scalars().all()
            project_id = parent.project_id
        if len(running) >= MAX_SUB_SESSIONS:
            return (
                f"Sub-session failed: at most {MAX_SUB_SESSIONS} children "
                "can run at once."
            )

        child_id = uuid.uuid4().hex
        try:
            prepared = await prepare_agent(
                self._context.factory,
                agent_name,
                self._context.project_root,
                self._context.skills_user_dir,
                session_id=child_id,
                session_mode="agent",
                media_max_dimension=self._context.media_max_dimension,
                media_max_bytes=self._context.media_max_bytes,
                web_config=self._context.web_config,
                extra_roots=self._context.extra_roots,
                compaction=self._context.compaction,
                sub_session_depth=self._context.depth + 1,
            )
        except (KeyError, ValueError) as exc:
            return f"Sub-session failed: {exc}"

        async with self._context.factory() as s:
            s.add(
                SessionRow(
                    id=child_id,
                    project_id=project_id,
                    agent_id=prepared.runtime.agent_id,
                    parent_session_id=parent_session_id,
                    sub_session_status="running",
                    sub_session_depth=self._context.depth + 1,
                )
            )
            await s.commit()

        def store_factory():
            return SQLiteMessageLogStore(self._context.factory, child_id)

        session = Session(
            session_id=child_id,
            project_root=self._context.project_root,
            agent_spec=prepared.spec,
            store=store_factory(),
            head_id=None,
            mode_name="agent",
        )
        harness = Harness(
            registry=prepared.registry,
            model=prepared.runtime.model,
            store_factory=store_factory,
            sub_session_runner=prepared.sub_session_runner,
            compaction=self._context.compaction,
        )
        bus = EventBus()
        try:
            run = await harness.run(session, text, bus)
        except Exception as exc:
            await _set_status(self._context.factory, child_id, "failed", str(exc))
            return f"Sub-session failed: {exc}"

        async def execute() -> str | None:
            try:
                outcome = await run.await_outcome()
                if outcome.status == "success":
                    result = await run.await_result()
                    context_tokens = context_tokens_from_usage(result.response.usage)
                    await session.append(
                        Turn(
                            id=uuid.uuid4().hex,
                            role="assistant",
                            content=str(result.output),
                            parent_id=session.head_id,
                            context_tokens=context_tokens,
                        ),
                        parent_id=session.head_id,
                    )
                    await _set_status(
                        self._context.factory,
                        child_id,
                        "completed",
                        output=str(result.output),
                    )
                    return str(result.output)
                if outcome.status == "cancelled":
                    run.cancel()
                    await _set_status(self._context.factory, child_id, "cancelled")
                    return None
                await _set_status(
                    self._context.factory,
                    child_id,
                    "failed",
                    outcome.message or "error",
                )
                return None
            except asyncio.CancelledError:
                run.cancel()
                await _set_status(self._context.factory, child_id, "cancelled")
                raise

        task_handle = asyncio.create_task(execute())
        _active[child_id] = (task_handle, run)

        if wait:
            output = await task_handle
            async with self._context.factory() as s:
                row = await s.get(SessionRow, child_id)
            status = row.sub_session_status if row else "failed"
            if output:
                return f"Sub-session {child_id} {status} ({agent_name}): {output}"
            error = (
                row.sub_session_error
                if row and row.sub_session_error
                else "no output"
            )
            return f"Sub-session {child_id} {status} ({agent_name}): {error}"

        return f"Started sub-session {child_id} with {agent_name}."

    async def list(self, parent_session_id: str) -> str:
        async with self._context.factory() as s:
            rows = (
                await s.execute(
                    select(SessionRow)
                    .where(SessionRow.parent_session_id == parent_session_id)
                    .order_by(SessionRow.created_at)  # ty: ignore[invalid-argument-type]
                )
            ).scalars().all()
        if not rows:
            return "No sub-sessions."
        lines = ["Sub-sessions:"]
        for row in rows:
            if row.sub_session_status != "running":
                _active.pop(row.id, None)
            elif row.id not in _active:
                await _set_status(
                    self._context.factory,
                    row.id,
                    "failed",
                    "interrupted by backend restart",
                )
                row.sub_session_status = "failed"
                row.sub_session_error = "interrupted by backend restart"
            task = await _first_user_text(self._context.factory, row.id)
            name = await _agent_name(self._context.factory, row.agent_id)
            lines.append(
                f"- {row.id} {row.sub_session_status or 'unknown'} "
                f"depth={row.sub_session_depth} agent={name} task={task[:80]}"
            )
        return "\n".join(lines)

    async def get(
        self, parent_session_id: str, sub_session_id: str, max_chars: int
    ) -> str:
        async with self._context.factory() as s:
            row = await s.get(SessionRow, sub_session_id)
        if row is None or row.parent_session_id != parent_session_id:
            return "Sub-session not found."
        if row.sub_session_status != "running":
            _active.pop(sub_session_id, None)
        elif sub_session_id not in _active:
            await _set_status(
                self._context.factory,
                sub_session_id,
                "failed",
                "interrupted by backend restart",
            )
            row.sub_session_status = "failed"
            row.sub_session_error = "interrupted by backend restart"
        limit = max(100, min(100_000, int(max_chars)))
        name = await _agent_name(self._context.factory, row.agent_id)
        task = await _first_user_text(self._context.factory, sub_session_id)
        output = row.sub_session_output or await _latest_assistant_text(
            self._context.factory, sub_session_id
        )
        lines = [
            f"Sub-session {sub_session_id}: {row.sub_session_status or 'unknown'} "
            f"(agent {name}, depth {row.sub_session_depth})",
            f"Task: {task}",
        ]
        if row.sub_session_error:
            lines.append(f"Error: {row.sub_session_error}")
        lines.append("Output:")
        lines.append((output or "(no output)")[:limit])
        return "\n".join(lines)

    async def cancel(self, parent_session_id: str, sub_session_id: str) -> str:
        async with self._context.factory() as s:
            row = await s.get(SessionRow, sub_session_id)
        if row is None or row.parent_session_id != parent_session_id:
            return "Sub-session not found."
        if row.sub_session_status != "running":
            return f"Sub-session {sub_session_id} is already {row.sub_session_status}."
        active = _active.pop(sub_session_id, None)
        if active is not None:
            task_handle, run = active
            run.cancel()
            task_handle.cancel()
        await _set_status(self._context.factory, sub_session_id, "cancelled")
        return f"Cancelled sub-session {sub_session_id}."


async def cancel_sub_sessions(factory, parent_session_id: str) -> None:
    async with factory() as s:
        rows = (
            await s.execute(
                select(SessionRow).where(
                    SessionRow.parent_session_id == parent_session_id,
                    SessionRow.sub_session_status == "running",
                )
            )
        ).scalars().all()
    for row in rows:
        active = _active.pop(row.id, None)
        if active is not None:
            task_handle, run = active
            run.cancel()
            task_handle.cancel()
        await _set_status(factory, row.id, "cancelled")


async def shutdown_sub_sessions() -> None:
    for _child_id, (task_handle, run) in list(_active.items()):
        run.cancel()
        task_handle.cancel()
    _active.clear()


async def reconcile_running_sub_sessions(factory) -> None:
    async with factory() as s:
        rows = (
            await s.execute(
                select(SessionRow).where(SessionRow.sub_session_status == "running")
            )
        ).scalars().all()
        for row in rows:
            row.sub_session_status = "failed"
            row.sub_session_error = "interrupted by backend restart"
            s.add(row)
        await s.commit()
