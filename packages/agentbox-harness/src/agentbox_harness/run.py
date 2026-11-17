import asyncio
from dataclasses import dataclass

from pydantic_ai import Agent, AgentRunResultEvent, CancellationToken

from agentbox_harness.events import EventBus, RunEvent


@dataclass
class Run:
    run_id: str
    task: asyncio.Task
    cancellation_token: CancellationToken | None = None

    async def await_result(self):
        return await self.task

    def cancel(self) -> None:
        if self.cancellation_token is not None:
            self.cancellation_token.cancel()


class RunManager:
    def __init__(self, model: str):
        self.model = model

    def start(
        self,
        agent: Agent,
        prompt: str,
        run_id: str,
        bus: EventBus,
        model_override=None,
        cancellation_token: CancellationToken | None = None,
    ) -> Run:
        task = asyncio.create_task(
            self._drive(agent, prompt, run_id, bus, model_override, cancellation_token)
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
    ):
        seq = 0
        kwargs = {"model": model_override} if model_override is not None else {}
        if cancellation_token is not None:
            kwargs["cancellation_token"] = cancellation_token
        final = None
        async with agent.run_stream_events(prompt, **kwargs) as events:
            async for event in events:
                bus.publish(RunEvent(run_id=run_id, seq=seq, event=event))
                seq += 1
                if isinstance(event, AgentRunResultEvent):
                    final = event.result
        return final
