"""Drive an agent stream as a background task and publish its events.

:class:`RunManager` starts a task that streams agent events onto the event bus.
A run retries once with replacement history when the model reports a context
window overflow and compaction recovers history.
"""

import asyncio
from dataclasses import dataclass

from pydantic_ai import Agent, AgentRunResultEvent, CancellationToken
from pydantic_ai.exceptions import ModelContextWindowExceededError

from agentbox_harness.errors import RunOutcome, normalize_error
from agentbox_harness.events import EventBus, RunEvent
from agentbox_harness.logging import log_exception


@dataclass
class Run:
    """Handle to a running agent task and the token that controls it."""

    run_id: str
    task: asyncio.Task
    cancellation_token: CancellationToken | None = None

    async def await_result(self):
        """Await and return the underlying agent result.

        Returns:
            The value produced by the agent task.

        Raises:
            BaseException: Whatever the task raised, including cancellation.
        """
        return await self.task

    async def await_outcome(self) -> RunOutcome:
        """Await the task and normalize any failure into a run outcome.

        Returns:
            A success outcome, or the normalized outcome for the raised
            exception.
        """
        try:
            await self.task
            return RunOutcome(status="success")
        except BaseException as exc:
            return normalize_error(exc)

    def cancel(self) -> None:
        """Request cancellation of the running task through its token."""
        if self.cancellation_token is not None:
            self.cancellation_token.cancel()


class RunManager:
    """Start agent runs as background tasks that publish bus events."""

    def start(
        self,
        agent: Agent,
        prompt: str,
        run_id: str,
        bus: EventBus,
        model_override=None,
        cancellation_token: CancellationToken | None = None,
        message_history=None,
        prompt_override=None,
        on_context_overflow=None,
    ) -> Run:
        """Start a managed run and return its handle.

        Args:
            agent: Agent to drive.
            prompt: Plain prompt passed to the agent.
            run_id: Identifier used to tag published events.
            bus: Event bus that receives streamed events.
            model_override: Optional model passed to the agent run.
            cancellation_token: Token used to cancel the run; a new token is
                created when omitted.
            message_history: Optional message history to seed the run.
            prompt_override: Structured prompt parts used instead of ``prompt``.
            on_context_overflow: Optional callback returning replacement
                history after a context-window error.

        Returns:
            A run handle owning the task and cancellation token.
        """
        # Each run gets its own token; that token is the cancellation boundary
        # and is reused across the context-overflow retry.
        cancellation_token = cancellation_token or CancellationToken()
        task = asyncio.create_task(
            self._drive(
                agent,
                prompt,
                run_id,
                bus,
                model_override,
                cancellation_token,
                message_history,
                prompt_override,
                on_context_overflow,
            )
        )
        return Run(run_id=run_id, task=task, cancellation_token=cancellation_token)

    async def _drive(
        self,
        agent: Agent,
        prompt: str,
        run_id: str,
        bus: EventBus,
        model_override=None,
        cancellation_token: CancellationToken | None = None,
        message_history=None,
        prompt_override=None,
        on_context_overflow=None,
    ):
        """Stream agent events onto the bus and retry once after overflow.

        The retry happens only when the model reports a context-window
        overflow and ``on_context_overflow`` returns replacement history; there
        is no backoff. Every failure path publishes a normalized error event
        before re-raising.
        """
        seq = 0
        prompt_arg = prompt_override if prompt_override is not None else prompt
        base_kwargs = {"model": model_override} if model_override is not None else {}
        if cancellation_token is not None:
            base_kwargs["cancellation_token"] = cancellation_token

        async def attempt(history):
            nonlocal seq
            kwargs = dict(base_kwargs)
            if history is not None:
                kwargs["message_history"] = history
            final = None
            async with agent.run_stream_events(prompt_arg, **kwargs) as events:
                async for event in events:
                    bus.publish(RunEvent(run_id=run_id, seq=seq, event=event))
                    seq += 1
                    if isinstance(event, AgentRunResultEvent):
                        final = event.result
            return final

        try:
            return await attempt(message_history)
        # The context-overflow branch is the only automatic retry: it reuses
        # the same token and runs exactly once, with no backoff.
        except ModelContextWindowExceededError as exc:
            if on_context_overflow is None:
                log_exception("run failed id={}", run_id)
                bus.publish(
                    RunEvent(run_id=run_id, seq=seq, event=normalize_error(exc))
                )
                raise
            try:
                new_history = await on_context_overflow()
            except BaseException:
                log_exception("context recovery failed id={}", run_id)
                bus.publish(
                    RunEvent(run_id=run_id, seq=seq, event=normalize_error(exc))
                )
                raise exc from None
            if new_history is None:
                log_exception("run failed id={}", run_id)
                bus.publish(
                    RunEvent(run_id=run_id, seq=seq, event=normalize_error(exc))
                )
                raise
            try:
                return await attempt(new_history)
            except BaseException as retry_exc:
                log_exception("run failed id={}", run_id)
                bus.publish(
                    RunEvent(
                        run_id=run_id,
                        seq=seq,
                        event=normalize_error(retry_exc),
                    )
                )
                raise
        except BaseException as exc:
            log_exception("run failed id={}", run_id)
            bus.publish(
                RunEvent(run_id=run_id, seq=seq, event=normalize_error(exc))
            )
            raise
