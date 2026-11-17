from pydantic_ai import Agent, CancellationToken
from pydantic_ai.models.test import TestModel

from agentbox_harness.events import EventBus
from agentbox_harness.run import RunManager


async def test_await_outcome_success():
    agent = Agent("test", instructions="echo")
    bus = EventBus()
    mgr = RunManager(model="test")
    run = mgr.start(agent, "hi", run_id="r1", bus=bus, model_override=TestModel())
    outcome = await run.await_outcome()
    assert outcome.status == "success"


async def test_await_outcome_cancelled():
    agent = Agent("test", instructions="echo")
    bus = EventBus()
    token = CancellationToken()
    mgr = RunManager(model="test")
    run = mgr.start(
        agent,
        "hi",
        run_id="r1",
        bus=bus,
        model_override=TestModel(),
        cancellation_token=token,
    )
    token.cancel()
    outcome = await run.await_outcome()
    assert outcome.status == "cancelled"
