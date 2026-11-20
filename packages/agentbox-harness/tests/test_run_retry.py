from contextlib import asynccontextmanager

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelContextWindowExceededError
from pydantic_ai.models.test import TestModel

from agentbox_harness.events import EventBus
from agentbox_harness.run import RunManager


class FlakyModel(TestModel):
    def __init__(self):
        super().__init__(custom_output_text="ok")
        self.calls = 0

    @asynccontextmanager
    async def request_stream(
        self, messages, model_settings, model_request_parameters, run_context=None
    ):
        self.calls += 1
        if self.calls == 1:
            raise ModelContextWindowExceededError("test", "too long")
        async with super().request_stream(
            messages,
            model_settings,
            model_request_parameters,
            run_context=run_context,
        ) as response:
            yield response


async def test_run_retries_once_on_context_overflow():
    model = FlakyModel()
    agent = Agent(model)
    bus = EventBus()
    recoveries = 0

    async def recover():
        nonlocal recoveries
        recoveries += 1
        return []

    run = RunManager().start(
        agent,
        "hi",
        "r1",
        bus,
        on_context_overflow=recover,
    )
    result = await run.await_result()
    assert result is not None
    assert model.calls == 2
    assert recoveries == 1
