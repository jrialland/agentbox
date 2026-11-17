from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from agentbox_harness.events import EventBus
from agentbox_harness.run import RunManager


async def test_run_emits_ordered_events():
    agent = Agent("test", instructions="echo")
    bus = EventBus()
    q = bus.subscribe()

    mgr = RunManager(model="test")
    run = mgr.start(agent, "hello", run_id="r1", bus=bus, model_override=TestModel())
    result = await run.await_result()
    bus.close()

    assert result.output is not None
    events = []
    while not q.empty():
        item = await q.get()
        if item is not None:
            events.append(item)
    seqs = [e.seq for e in events]
    assert seqs == sorted(seqs)
    assert len(events) > 0
