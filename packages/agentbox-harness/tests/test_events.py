from dataclasses import dataclass

from agentbox_harness.events import EventBus, RunEvent


@dataclass
class FakeEvent:
    text: str


async def test_event_bus_delivers_in_order():
    bus = EventBus()
    sub = bus.subscribe()

    bus.publish(RunEvent(run_id="r1", seq=0, event=FakeEvent("a")))
    bus.publish(RunEvent(run_id="r1", seq=1, event=FakeEvent("b")))
    bus.close()

    got = [e async for e in sub.stream()]
    assert [e.seq for e in got] == [0, 1]
    assert [e.event.text for e in got] == ["a", "b"]


async def test_snapshot_replays_past_events():
    bus = EventBus()
    bus.publish(RunEvent(run_id="r1", seq=0, event=FakeEvent("a")))
    bus.publish(RunEvent(run_id="r1", seq=1, event=FakeEvent("b")))

    sub = bus.subscribe()
    bus.close()

    got = [e async for e in sub.stream()]
    assert [e.seq for e in got] == [0, 1]


async def test_detach_stops_delivery():
    bus = EventBus()
    sub = bus.subscribe()
    sub.detach()

    bus.publish(RunEvent(run_id="r1", seq=0, event=FakeEvent("a")))
    bus.close()

    assert sub.queue.empty()


async def test_reattach_replays_and_continues():
    bus = EventBus()
    sub = bus.subscribe()
    bus.publish(RunEvent(run_id="r1", seq=0, event=FakeEvent("a")))
    sub.detach()
    bus.publish(RunEvent(run_id="r1", seq=1, event=FakeEvent("b")))

    sub2 = bus.subscribe()
    bus.close()

    got = [e async for e in sub2.stream()]
    assert [e.seq for e in got] == [0, 1]
