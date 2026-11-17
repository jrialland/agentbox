import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class RunEvent:
    run_id: str
    seq: int
    event: object


@dataclass
class Subscription:
    bus: "EventBus"
    id: int
    snapshot: list[RunEvent]
    queue: asyncio.Queue

    def detach(self) -> None:
        self.bus.unsubscribe(self.id)

    async def stream(self):
        for event in self.snapshot:
            yield event
        while True:
            item = await self.queue.get()
            if item is None:
                return
            yield item


class EventBus:
    def __init__(self) -> None:
        self._history: list[RunEvent] = []
        self._subscribers: dict[int, asyncio.Queue] = {}
        self._next_id = 0
        self._closed = False

    def subscribe(self) -> Subscription:
        q: asyncio.Queue = asyncio.Queue()
        sub_id = self._next_id
        self._next_id += 1
        self._subscribers[sub_id] = q
        return Subscription(bus=self, id=sub_id, snapshot=list(self._history), queue=q)

    def unsubscribe(self, sub_id: int) -> None:
        self._subscribers.pop(sub_id, None)

    def publish(self, event: RunEvent) -> None:
        self._history.append(event)
        for q in self._subscribers.values():
            q.put_nowait(event)

    def close(self) -> None:
        self._closed = True
        for q in self._subscribers.values():
            q.put_nowait(None)
