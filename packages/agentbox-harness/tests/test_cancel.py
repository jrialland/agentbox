import pytest
from pydantic_ai import Agent, CancellationToken, RunCancelled
from pydantic_ai.models.test import TestModel

from agentbox_harness.events import EventBus
from agentbox_harness.run import RunManager


async def test_cancel_raises_run_cancelled():
    agent = Agent("test", instructions="echo")
    bus = EventBus()
    token = CancellationToken()

    mgr = RunManager()
    run = mgr.start(
        agent,
        "hello",
        run_id="r1",
        bus=bus,
        model_override=TestModel(),
        cancellation_token=token,
    )
    token.cancel()

    with pytest.raises(RunCancelled):
        await run.await_result()


async def test_run_cancel_creates_a_token_when_none_is_given():
    agent = Agent("test", instructions="echo")
    mgr = RunManager()
    run = mgr.start(agent, "hello", run_id="r2", bus=EventBus(), model_override=TestModel())

    assert run.cancellation_token is not None
    run.cancel()
    with pytest.raises(RunCancelled):
        await run.await_result()
