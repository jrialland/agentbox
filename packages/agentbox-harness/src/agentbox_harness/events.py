"""In-process event bus for streaming run events.

The bus retains published events so a new subscriber can replay history before
receiving live events.
"""

import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class RunEvent:
    """An ordered event emitted during a run."""

    run_id: str
    seq: int
    event: object


@dataclass
class Subscription:
    """A subscriber's replay snapshot and live event queue."""

    bus: "EventBus"
    id: int
    snapshot: list[RunEvent]
    queue: asyncio.Queue

    def detach(self) -> None:
        """Unsubscribe this subscription from its bus."""
        self.bus.unsubscribe(self.id)

    async def stream(self):
        """Yield the buffered snapshot, then live events until the bus closes."""
        for event in self.snapshot:
            yield event
        while True:
            item = await self.queue.get()
            if item is None:
                return
            yield item


class EventBus:
    """Fan out run events to subscribers and retain them for replay.

    Subscribers receive a snapshot of history at subscribe time, then live
    events through an ``asyncio.Queue``. Closing the bus sends a ``None``
    sentinel to end each stream.
    """

    def __init__(self) -> None:  # noqa: D107
        self._history: list[RunEvent] = []
        self._subscribers: dict[int, asyncio.Queue] = {}
        self._next_id = 0
        self._closed = False

    def subscribe(self) -> Subscription:
        """Register a subscriber and capture the current event history."""
        q: asyncio.Queue = asyncio.Queue()
        sub_id = self._next_id
        self._next_id += 1
        self._subscribers[sub_id] = q
        return Subscription(bus=self, id=sub_id, snapshot=list(self._history), queue=q)

    def unsubscribe(self, sub_id: int) -> None:
        """Remove a subscriber by id; unknown ids are ignored."""
        self._subscribers.pop(sub_id, None)

    def publish(self, event: RunEvent) -> None:
        """Append an event to history and deliver it to live subscribers."""
        self._history.append(event)
        for q in self._subscribers.values():
            q.put_nowait(event)

    def close(self) -> None:
        """Mark the bus closed and terminate every subscriber stream."""
        self._closed = True
        for q in self._subscribers.values():
            q.put_nowait(None)
