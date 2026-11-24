"""Manage subagent sessions spawned by a parent session.

A subagent session is a child session created from a selected Agent
configuration (the subagent). This module owns the in-process job registry,
the tool-facing runner that starts/lists/waits/cancels child sessions, and the
reconciliation helpers used at startup and shutdown. Lifecycle boundaries are
explicit: starting captures the task and records a running row, completion sets
the job's ``done`` event, waits observe that event with a bounded timeout, and
cancellation propagates to descendants before marking rows cancelled.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
)
from sqlmodel import select

from agentbox_api.lsp_runtime import lsp_reminders
from agentbox_api.skills import prepare_agent
from agentbox_harness.compaction import CompactionConfig
from agentbox_harness.context_editing import ContextEditingConfig
from agentbox_harness.events import EventBus
from agentbox_harness.harness import Harness
from agentbox_harness.run import Run
from agentbox_harness.session import Session, Turn
from agentbox_harness.tools.web import WebToolConfig
from agentbox_harness.usage import context_tokens_from_usage
from agentbox_models.repos.message_log import DatabaseMessageLogStore
from agentbox_models.tables.core import Agent, SessionRow, TurnRow

MAX_SUBAGENT_SESSIONS = 5
MAX_SUBAGENT_SESSION_DEPTH = 3
OUTPUT_LIMIT = 200_000


@dataclass(frozen=True)
class SubagentSessionContext:
    """Immutable configuration shared by every subagent session of a parent.

    Captures the session factory, project and skill roots, model/tool config,
    and plugin and media options so child sessions inherit the parent's runtime
    environment. ``depth`` is the current nesting level; children run at
    ``depth + 1``.
    """

    factory: Any
    project_root: str
    skills_user_dir: str
    extra_roots: list[str]
    web_config: WebToolConfig | None
    compaction: CompactionConfig
    media_max_dimension: int
    media_max_bytes: int
    depth: int
    context_editing: ContextEditingConfig | None = None
    project_id: str | None = None
    plugins_user_dir: str | None = None
    plugins_data_dir: str | None = None


@dataclass
class SubagentSessionJob:
    """In-process state for one running or finished subagent session.

    The job tracks status, timing, captured output, and the run/task handles
    needed to cancel it. ``done`` signals job completion (success, failure, or
    cancellation); setting it is idempotent and is what waiters block on.
    """

    session_id: str
    parent_session_id: str
    subagent: str
    task: str
    depth: int
    status: str = "running"
    started_at: float = field(default_factory=time.monotonic)
    ended_at: float | None = None
    output: list[str] = field(default_factory=list)
    truncated: bool = False
    run: Run | None = None
    task_handle: asyncio.Task | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)
    result: str | None = None
    error: str | None = None

    def add_output(self, text: str) -> None:
        """Append streamed output, trimming the oldest text past the limit.

        Args:
            text: Contiguous chunk of output text; empty chunks are ignored.
        """
        if not text:
            return
        self.output.append(text)
        total = sum(len(part) for part in self.output)
        while total > OUTPUT_LIMIT and self.output:
            overflow = total - OUTPUT_LIMIT
            first = self.output[0]
            if len(first) <= overflow:
                self.output.pop(0)
                total -= len(first)
            else:
                self.output[0] = first[overflow:]
                total -= overflow
        self.truncated = total >= OUTPUT_LIMIT

    def output_text(self) -> str:
        """Return the currently buffered output joined into one string."""
        return "".join(self.output)


def _age_seconds(created_at: datetime) -> float:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return (datetime.now(UTC) - created_at).total_seconds()


async def _set_status(
    factory,
    session_id: str,
    status: str,
    error: str | None = None,
    output: str | None = None,
) -> None:
    async with factory() as s:
        row = await s.get(SessionRow, session_id)
        if row is None:
            return
        row.subagent_session_status = status
        row.subagent_session_error = error
        if output is not None:
            row.subagent_session_output = output
        s.add(row)
        await s.commit()


async def _child_rows(factory, parent_session_id: str):
    async with factory() as s:
        return (
            (
                await s.execute(
                    select(SessionRow)
                    .where(SessionRow.parent_session_id == parent_session_id)
                    .order_by(SessionRow.created_at.desc())  # ty: ignore[missing-attribute]
                )
            )
            .scalars()
            .all()
        )


async def _descendant_ids(factory, root_id: str) -> list[str]:
    ids: list[str] = []
    frontier = [root_id]
    while frontier:
        current = frontier.pop()
        for row in await _child_rows(factory, current):
            ids.append(row.id)
            frontier.append(row.id)
    return ids


async def _first_user_text(factory, session_id: str) -> str:
    async with factory() as s:
        row = (
            await s.execute(
                select(TurnRow)
                .where(TurnRow.session_id == session_id, TurnRow.role == "user")
                .order_by(TurnRow.created_at)  # ty: ignore[invalid-argument-type]
            )
        ).scalars().first()
    return row.content if row else ""


async def _latest_assistant_text(factory, session_id: str) -> str:
    async with factory() as s:
        row = (
            await s.execute(
                select(TurnRow)
                .where(
                    TurnRow.session_id == session_id,
                    TurnRow.role == "assistant",
                )
                .order_by(TurnRow.created_at.desc())  # ty: ignore[missing-attribute]
            )
        ).scalars().first()
    return row.content if row else ""


async def _agent_name(factory, agent_id: str) -> str:
    async with factory() as s:
        row = await s.get(Agent, agent_id)
    return row.name if row else agent_id


def _event_text(event) -> str | None:
    if isinstance(event, PartStartEvent):
        part = event.part
        if isinstance(part, TextPart) and part.content:
            return part.content
        return None
    if isinstance(event, PartDeltaEvent):
        delta = event.delta
        if isinstance(delta, TextPartDelta) and delta.content_delta:
            return delta.content_delta
        return None
    if isinstance(event, FunctionToolCallEvent):
        name = getattr(event.part, "tool_name", None) or getattr(
            event.part, "tool_call_id", "tool"
        )
        return f"\n[tool] {name}: started\n"
    if isinstance(event, FunctionToolResultEvent):
        name = getattr(event.part, "tool_name", None) or getattr(
            event.part, "tool_call_id", "tool"
        )
        return f"\n[tool] {name}: completed\n"
    return None


class SubagentSessionManager:
    """Registry of live subagent-session jobs keyed by session id.

    The registry is process-local and is the source of truth for cancellation
    and waiting; persisted rows hold the durable status used after restarts.
    """

    def __init__(self) -> None:
        """Create an empty registry of subagent-session jobs."""
        self._jobs: dict[str, SubagentSessionJob] = {}

    def register(self, job: SubagentSessionJob) -> None:
        """Register a newly started subagent-session job.

        Args:
            job: The job to track under its ``session_id``.
        """
        self._jobs[job.session_id] = job

    def get(self, session_id: str) -> SubagentSessionJob | None:
        """Return the tracked job for ``session_id``, if still registered.

        Args:
            session_id: Subagent session id to look up.

        Returns:
            The job, or ``None`` when it is not tracked in this process.
        """
        return self._jobs.get(session_id)

    def children(self, parent_session_id: str) -> list[SubagentSessionJob]:
        """Return the tracked direct children of ``parent_session_id``.

        Args:
            parent_session_id: Parent session id whose children to list.

        Returns:
            Jobs whose ``parent_session_id`` matches.
        """
        return [
            job
            for job in self._jobs.values()
            if job.parent_session_id == parent_session_id
        ]

    async def wait(self, job: SubagentSessionJob, timeout: int) -> None:
        """Wait up to ``timeout`` seconds for ``job`` to finish.

        The timeout is clamped to ``[1, 600]`` seconds. A timeout is not an
        error: the job keeps running and the caller inspects its current state.

        Args:
            job: Job to wait on.
            timeout: Maximum seconds to wait, clamped to the allowed range.
        """
        timeout = max(1, min(600, int(timeout)))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(job.done.wait(), timeout)

    async def wait_many(
        self, jobs: list[SubagentSessionJob], mode: str, timeout: int
    ) -> None:
        """Wait for several jobs, either for all or for the first to finish.

        Args:
            jobs: Jobs to wait on; empty means return immediately.
            mode: ``"any"`` to stop at the first completion, otherwise wait for
                all.
            timeout: Maximum seconds to wait, clamped to ``[1, 600]``.
        """
        if not jobs:
            return
        timeout = max(1, min(600, int(timeout)))
        waiters = [asyncio.create_task(self.wait(job, timeout)) for job in jobs]
        if mode == "any":
            _, pending = await asyncio.wait(
                waiters,
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            # In "any" mode the remaining waiters are cancelled so their tasks
            # do not linger after the first job completes.
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        else:
            await asyncio.gather(*waiters)

    def cancel(self, session_id: str) -> None:
        """Cancel a subagent session and all of its descendants.

        Cancellation is depth-first over tracked children. The job's run and
        task are cancelled when present, its status becomes ``cancelled`` if it
        was still running, and ``done`` is set so waiters unblock.

        Args:
            session_id: Subagent session to cancel; unknown ids are a no-op.
        """
        job = self._jobs.get(session_id)
        if job is None:
            return
        for child in [
            item
            for item in self._jobs.values()
            if item.parent_session_id == session_id
        ]:
            self.cancel(child.session_id)
        if job.run is not None:
            job.run.cancel()
        if job.task_handle is not None:
            job.task_handle.cancel()
        if job.status == "running":
            job.status = "cancelled"
            job.ended_at = time.monotonic()
        job.done.set()

    async def shutdown(self) -> None:
        """Cancel every tracked job and clear the registry."""
        for job in list(self._jobs.values()):
            self.cancel(job.session_id)
        self._jobs.clear()


_manager: SubagentSessionManager | None = None


def get_subagent_session_manager() -> SubagentSessionManager:
    """Return the process-wide subagent-session manager, creating it lazily.

    Returns:
        The shared :class:`SubagentSessionManager` singleton.
    """
    global _manager
    if _manager is None:
        _manager = SubagentSessionManager()
    return _manager


def reset_subagent_session_manager() -> None:
    """Drop the process-wide manager so the next lookup builds a fresh one.

    Used by tests and by startup paths that need a clean registry.
    """
    global _manager
    _manager = None


class ApiSubagentSessionRunner:
    """Tool-facing runner that starts and manages parent-owned child sessions.

    Implements the harness subagent-session runner interface. Every method
    treats ``parent_session_id`` as the ownership boundary: a child is only
    visible, waited on, or cancelled through the parent that spawned it.
    """

    def __init__(self, context: SubagentSessionContext):
        """Bind the runner to a parent's context and the shared manager.

        Args:
            context: Parent-owned context child sessions inherit from.
        """
        self._context = context
        self._manager = get_subagent_session_manager()

    async def list_agents(self) -> str:
        """List the Agent configurations available as subagents.

        Returns:
            A newline-delimited listing, or ``"No agents."`` when none exist.
        """
        async with self._context.factory() as s:
            rows = (
                await s.execute(select(Agent).order_by(Agent.name))
            ).scalars().all()
        if not rows:
            return "No agents."
        lines = ["Agents:"]
        for row in rows:
            lines.append(f"- {row.name}: {row.description}")
        return "\n".join(lines)

    async def start(
        self,
        parent_session_id: str,
        subagent: str,
        task: str,
        wait: bool,
    ) -> str:
        """Start a subagent session using an Agent configuration.

        Enforces the non-empty task, maximum nesting depth, and the limit on
        concurrently running children. On success the child session row is
        created and a task is dispatched; with ``wait`` the call blocks until
        the job's ``done`` event is set and returns its summary, otherwise it
        returns immediately with the new session id.

        Args:
            parent_session_id: Session that owns the new child session.
            subagent: Name of the Agent configuration to run.
            task: User message the child session runs with.
            wait: Whether to block for completion before returning.

        Returns:
            A status or summary string suitable for returning to the model.
        """
        text = (task or "").strip()
        if not text:
            return "Subagent session failed: task must not be empty."
        if self._context.depth >= MAX_SUBAGENT_SESSION_DEPTH:
            return "Subagent session failed: maximum depth reached."

        async with self._context.factory() as s:
            parent = await s.get(SessionRow, parent_session_id)
            if parent is None:
                return "Subagent session failed: parent session not found."
            running = (
                await s.execute(
                    select(SessionRow).where(
                        SessionRow.parent_session_id == parent_session_id,
                        SessionRow.subagent_session_status == "running",
                    )
                )
            ).scalars().all()
            project_id = parent.project_id
        if len(running) >= MAX_SUBAGENT_SESSIONS:
            return (
                f"Subagent session failed: at most {MAX_SUBAGENT_SESSIONS} "
                "children can run at once."
            )

        child_id = uuid.uuid4().hex
        try:
            prepared = await prepare_agent(
                self._context.factory,
                subagent,
                self._context.project_root,
                self._context.skills_user_dir,
                session_id=child_id,
                session_mode="agent",
                media_max_dimension=self._context.media_max_dimension,
                media_max_bytes=self._context.media_max_bytes,
                web_config=self._context.web_config,
                extra_roots=self._context.extra_roots,
                context_editing=self._context.context_editing,
                project_id=self._context.project_id,
                plugins_user_dir=self._context.plugins_user_dir,
                plugins_data_dir=self._context.plugins_data_dir,
                compaction=self._context.compaction,
                subagent_session_depth=self._context.depth + 1,
            )
        except KeyError:
            return f"Subagent session failed: unknown agent {subagent}."
        except ValueError as exc:
            return f"Subagent session failed: {exc}"

        async with self._context.factory() as s:
            s.add(
                SessionRow(
                    id=child_id,
                    project_id=project_id,
                    agent_id=prepared.runtime.agent_id,
                    parent_session_id=parent_session_id,
                    subagent_session_status="running",
                    subagent_session_depth=self._context.depth + 1,
                )
            )
            await s.commit()

        job = SubagentSessionJob(
            session_id=child_id,
            parent_session_id=parent_session_id,
            subagent=subagent,
            task=text,
            depth=self._context.depth + 1,
        )
        self._manager.register(job)
        job.task_handle = asyncio.create_task(self._execute(job, prepared, text))

        if wait:
            await job.done.wait()
            return await self._summary(parent_session_id, child_id, 4000)
        return f"Started subagent session {child_id} with {subagent}."

    async def _execute(self, job, prepared, text: str) -> None:
        def store_factory():
            return DatabaseMessageLogStore(self._context.factory, job.session_id)

        session = Session(
            session_id=job.session_id,
            project_root=self._context.project_root,
            agent_spec=prepared.spec,
            store=store_factory(),
            head_id=None,
            mode_name="agent",
            extra_roots=self._context.extra_roots,
            plugin_roots=[str(path) for path in prepared.plugin_roots],
        )
        harness = Harness(
            registry=prepared.registry,
            model=prepared.runtime.model,
            store_factory=store_factory,
            compaction=self._context.compaction,
            subagent_session_runner=prepared.subagent_session_runner,
            reminders=lsp_reminders(),
            context_editing=self._context.context_editing,
            plugin_hooks=prepared.plugin_hooks,
        )
        bus = EventBus()
        subscription = bus.subscribe()
        drain_task = asyncio.create_task(self._drain(subscription, job))
        try:
            warnings = (await harness.prepare_mcp(session)).warnings
            for warning in warnings:
                logger.warning(
                    "subagent session mcp server unavailable session={} server={} error={}",
                    job.session_id,
                    warning.server_id,
                    warning.message,
                )
            run = await harness.run(session, text, bus)
            job.run = run
            outcome = await run.await_outcome()
            if outcome.status == "success":
                result = await run.await_result()
                output = str(result.output)
                context_tokens = context_tokens_from_usage(result.response.usage)
                await session.append(
                    Turn(
                        id=uuid.uuid4().hex,
                        role="assistant",
                        content=output,
                        parent_id=session.head_id,
                        context_tokens=context_tokens,
                    ),
                    parent_id=session.head_id,
                )
                job.status = "completed"
                job.result = output
                await _set_status(
                    self._context.factory, job.session_id, "completed", output=output
                )
            elif outcome.status == "cancelled":
                run.cancel()
                job.status = "cancelled"
                await _set_status(self._context.factory, job.session_id, "cancelled")
            else:
                job.status = "failed"
                job.error = outcome.message or "error"
                await _set_status(
                    self._context.factory,
                    job.session_id,
                    "failed",
                    job.error,
                )
        except asyncio.CancelledError:
            job.status = "cancelled"
            await _set_status(self._context.factory, job.session_id, "cancelled")
            raise
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            logger.warning(
                "subagent session failed session={} error={}", job.session_id, exc
            )
            await _set_status(
                self._context.factory,
                job.session_id,
                "failed",
                job.error,
            )
        finally:
            bus.close()
            with contextlib.suppress(asyncio.CancelledError):
                await drain_task
            job.ended_at = time.monotonic()
            job.done.set()

    async def _drain(self, subscription, job) -> None:
        async for item in subscription.stream():
            text = _event_text(item.event)
            if text:
                job.add_output(text)

    async def list(self, parent_session_id: str) -> str:
        """List the child sessions spawned by ``parent_session_id``.

        Args:
            parent_session_id: Parent session whose children to list.

        Returns:
            A newline-delimited listing, or ``"No subagent sessions."``.
        """
        rows = await _child_rows(self._context.factory, parent_session_id)
        if not rows:
            return "No subagent sessions."
        lines = ["Subagent sessions:"]
        for row in rows:
            job = self._manager.get(row.id)
            status = job.status if job else (row.subagent_session_status or "unknown")
            depth = job.depth if job else row.subagent_session_depth
            name = (
                job.subagent
                if job
                else await _agent_name(self._context.factory, row.agent_id)
            )
            task = (
                job.task
                if job
                else await _first_user_text(self._context.factory, row.id)
            )
            if job:
                age = (job.ended_at or time.monotonic()) - job.started_at
            else:
                age = _age_seconds(row.created_at)
            duration = (
                f" duration={(job.ended_at - job.started_at):.1f}s"
                if job is not None and job.ended_at is not None
                else ""
            )
            lines.append(
                f"- {row.id} {status} subagent={name} depth={depth} "
                f"age={age:.1f}s{duration} task={task[:80]}"
            )
        return "\n".join(lines)

    async def get(
        self, parent_session_id: str, subagent_session_id: str, max_chars: int
    ) -> str:
        """Return a bounded summary of one child session's output and status.

        Ownership is checked by ``parent_session_id``; a child that does not
        belong to the parent is reported as not found.

        Args:
            parent_session_id: Parent session used for the ownership check.
            subagent_session_id: Child session to summarize.
            max_chars: Maximum output characters to include (clamped).

        Returns:
            A formatted summary string.
        """
        return await self._summary(parent_session_id, subagent_session_id, max_chars)

    async def _summary(
        self, parent_session_id: str, subagent_session_id: str, max_chars: int
    ) -> str:
        async with self._context.factory() as s:
            row = await s.get(SessionRow, subagent_session_id)
        if row is None or row.parent_session_id != parent_session_id:
            return "Subagent session not found."

        job = self._manager.get(subagent_session_id)
        status = job.status if job else (row.subagent_session_status or "unknown")
        depth = job.depth if job else row.subagent_session_depth
        name = (
            job.subagent
            if job
            else await _agent_name(self._context.factory, row.agent_id)
        )
        task = (
            job.task
            if job
            else await _first_user_text(self._context.factory, subagent_session_id)
        )
        if job and job.status == "running":
            output = job.output_text()
        else:
            output = row.subagent_session_output or await _latest_assistant_text(
                self._context.factory, subagent_session_id
            )
            if not output and job:
                output = job.result or job.error or job.output_text()
        error = job.error if job else row.subagent_session_error
        limit = max(100, min(100_000, int(max_chars)))
        lines = [
            f"Subagent session {subagent_session_id}: {status} "
            f"(subagent {name}, depth {depth})",
            f"Task: {task}",
        ]
        if error:
            lines.append(f"Error: {error}")
        lines.append("Output:")
        lines.append((output or "(no output)")[:limit])
        return "\n".join(lines)

    async def cancel(self, parent_session_id: str, subagent_session_id: str) -> str:
        """Cancel a child session and its descendants through ``parent_session_id``.

        The child must belong to the parent and still be running. Cancellation
        signals each tracked job, waits briefly for their tasks, then marks the
        persisted rows cancelled so state survives the process.

        Args:
            parent_session_id: Parent session used for the ownership check.
            subagent_session_id: Child session to cancel.

        Returns:
            A status string describing the outcome.
        """
        async with self._context.factory() as s:
            row = await s.get(SessionRow, subagent_session_id)
        if row is None or row.parent_session_id != parent_session_id:
            return "Subagent session not found."
        if row.subagent_session_status != "running":
            return (
                f"Subagent session {subagent_session_id} is already "
                f"{row.subagent_session_status}."
            )

        ids = [
            subagent_session_id,
            *await _descendant_ids(self._context.factory, subagent_session_id),
        ]
        tasks = []
        for sid in ids:
            job = self._manager.get(sid)
            if job is not None and job.task_handle is not None:
                tasks.append(job.task_handle)
            self._manager.cancel(sid)
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=5)
            for task in pending:
                task.cancel()
        async with self._context.factory() as s:
            for sid in ids:
                target = await s.get(SessionRow, sid)
                if target is not None and target.subagent_session_status == "running":
                    target.subagent_session_status = "cancelled"
                    s.add(target)
            await s.commit()
        return f"Cancelled subagent session {subagent_session_id}."

    async def wait(
        self, parent_session_id: str, subagent_session_id: str, timeout: int
    ) -> str:
        """Wait for a single child session, bounded by ``timeout`` seconds.

        Waiting observes the job's ``done`` event; if the job is not running or
        is not tracked in this process, the current summary is returned
        immediately.

        Args:
            parent_session_id: Parent session used for the ownership check.
            subagent_session_id: Child session to wait on.
            timeout: Maximum seconds to wait.

        Returns:
            The child session summary after waiting.
        """
        async with self._context.factory() as s:
            row = await s.get(SessionRow, subagent_session_id)
        if row is None or row.parent_session_id != parent_session_id:
            return "Subagent session not found."
        job = self._manager.get(subagent_session_id)
        if job is not None and job.status == "running":
            await self._manager.wait(job, timeout)
        return await self._summary(parent_session_id, subagent_session_id, 4000)

    async def wait_many(
        self,
        parent_session_id: str,
        subagent_session_ids: Sequence[str],
        mode: str,
        timeout: int,
    ) -> str:
        """Wait for several child sessions and return a summary for each.

        Only running jobs tracked in this process are waited on; the persisted
        rows of untracked or finished sessions are summarized directly.

        Args:
            parent_session_id: Parent session used for the ownership check.
            subagent_session_ids: Child sessions to wait on.
            mode: ``"all"`` to wait for every job or ``"any"`` for the first.
            timeout: Maximum seconds to wait.

        Returns:
            A double-newline separated block per child session.
        """
        if not subagent_session_ids:
            return "No subagent sessions."
        if mode not in {"all", "any"}:
            return "Subagent session failed: mode must be 'all' or 'any'."

        jobs = []
        missing: list[str] = []
        for sid in subagent_session_ids:
            async with self._context.factory() as s:
                row = await s.get(SessionRow, sid)
            if row is None or row.parent_session_id != parent_session_id:
                missing.append(sid)
                continue
            job = self._manager.get(sid)
            if job is not None and job.status == "running":
                jobs.append(job)
        if jobs:
            await self._manager.wait_many(jobs, mode, timeout)

        lines: list[str] = []
        for sid in subagent_session_ids:
            if sid in missing:
                lines.append(f"- {sid}: Subagent session not found.")
            else:
                lines.append(await self._summary(parent_session_id, sid, 4000))
        return "\n\n".join(lines)


async def cancel_subagent_sessions(factory, parent_session_id: str) -> None:
    """Cancel every descendant subagent session of ``parent_session_id``.

    Used when a parent session is deleted or stopped. Each descendant whose
    tracked job is live is signalled, then running rows are marked cancelled.

    Args:
        factory: Async session factory for reading and updating rows.
        parent_session_id: Root session whose descendants to cancel.
    """
    manager = get_subagent_session_manager()
    ids = await _descendant_ids(factory, parent_session_id)
    for sid in ids:
        manager.cancel(sid)
    async with factory() as s:
        for sid in ids:
            row = await s.get(SessionRow, sid)
            if row is not None and row.subagent_session_status == "running":
                row.subagent_session_status = "cancelled"
                s.add(row)
        await s.commit()


async def shutdown_subagent_sessions() -> None:
    """Cancel all tracked subagent sessions during application shutdown."""
    await get_subagent_session_manager().shutdown()


async def reconcile_running_subagent_sessions(factory) -> None:
    """Mark rows still recorded as running as failed after a restart.

    In-process jobs do not survive a backend restart, so any persisted
    ``running`` child status is stale and is reset to ``failed`` with a restart
    reason.

    Args:
        factory: Async session factory used to read and update child rows.
    """
    async with factory() as s:
        rows = (
            await s.execute(
                select(SessionRow).where(
                    SessionRow.subagent_session_status == "running"
                )
            )
        ).scalars().all()
        for row in rows:
            row.subagent_session_status = "failed"
            row.subagent_session_error = "interrupted by backend restart"
            s.add(row)
        await s.commit()
