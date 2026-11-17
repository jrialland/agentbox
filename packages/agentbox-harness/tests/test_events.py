from dataclasses import dataclass

from agentbox_harness.events import EventBus, RunEvent


@dataclass
class FakeEvent:
    text: str


async def test_event_bus_delivers_in_order():
    bus = EventBus()
    q = bus.subscribe()

    bus.publish(RunEvent(run_id="r1", seq=0, event=FakeEvent("a")))
    bus.publish(RunEvent(run_id="r1", seq=1, event=FakeEvent("b")))
    bus.close()

    got = []
    while not q.empty():
        item = await q.get()
        if item is not None:
            got.append(item)

    assert [e.seq for e in got] == [0, 1]
    assert [e.event.text for e in got] == ["a", "b"]


async def test_multiple_subscribers_each_get_every_event():
    bus = EventBus()
    q1 = bus.subscribe()
    q2 = bus.subscribe()
    bus.publish(RunEvent(run_id="r1", seq=0, event=FakeEvent("x")))
    bus.close()
    assert await q1.get() == await q2.get()
