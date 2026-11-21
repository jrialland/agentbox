import asyncio
from dataclasses import dataclass

from loguru import logger
from pydantic_ai import Agent, AgentRunResultEvent, CancellationToken
from pydantic_ai.exceptions import ModelContextWindowExceededError

from agentbox_harness.errors import RunOutcome, normalize_error
from agentbox_harness.events import EventBus, RunEvent


@dataclass
class Run:
    run_id: str
    task: asyncio.Task
    cancellation_token: CancellationToken | None = None

    async def await_result(self):
        return await self.task

    async def await_outcome(self) -> RunOutcome:
        try:
            await self.task
            return RunOutcome(status="success")
        except BaseException as exc:
            return normalize_error(exc)

    def cancel(self) -> None:
        if self.cancellation_token is not None:
            self.cancellation_token.cancel()


class RunManager:
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
        except ModelContextWindowExceededError as exc:
            if on_context_overflow is None:
                logger.exception("run failed id={}", run_id)
                bus.publish(
                    RunEvent(run_id=run_id, seq=seq, event=normalize_error(exc))
                )
                raise
            try:
                new_history = await on_context_overflow()
            except BaseException:
                logger.exception("context recovery failed id={}", run_id)
                bus.publish(
                    RunEvent(run_id=run_id, seq=seq, event=normalize_error(exc))
                )
                raise exc from None
            if new_history is None:
                logger.exception("run failed id={}", run_id)
                bus.publish(
                    RunEvent(run_id=run_id, seq=seq, event=normalize_error(exc))
                )
                raise
            try:
                return await attempt(new_history)
            except BaseException as retry_exc:
                logger.exception("run failed id={}", run_id)
                bus.publish(
                    RunEvent(
                        run_id=run_id,
                        seq=seq,
                        event=normalize_error(retry_exc),
                    )
                )
                raise
        except BaseException as exc:
            logger.exception("run failed id={}", run_id)
            bus.publish(
                RunEvent(run_id=run_id, seq=seq, event=normalize_error(exc))
            )
            raise
