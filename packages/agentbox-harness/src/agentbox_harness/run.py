import asyncio
from dataclasses import dataclass

from pydantic_ai import Agent, AgentRunResultEvent

from agentbox_harness.events import EventBus, RunEvent


@dataclass
class Run:
    run_id: str
    task: asyncio.Task

    async def await_result(self):
        return await self.task


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
    ) -> Run:
        task = asyncio.create_task(
            self._drive(agent, prompt, run_id, bus, model_override)
        )
        return Run(run_id=run_id, task=task)

    async def _drive(
        self,
        agent: Agent,
        prompt: str,
        run_id: str,
        bus: EventBus,
        model_override=None,
    ):
        seq = 0
        kwargs = {"model": model_override} if model_override is not None else {}
        final = None
        async with agent.run_stream_events(prompt, **kwargs) as events:
            async for event in events:
                bus.publish(RunEvent(run_id=run_id, seq=seq, event=event))
                seq += 1
                if isinstance(event, AgentRunResultEvent):
                    final = event.result
        return final
