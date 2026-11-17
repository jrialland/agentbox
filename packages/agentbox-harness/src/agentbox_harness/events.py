import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class RunEvent:
    run_id: str
    seq: int
    event: object


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []
        self._closed = False

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def publish(self, event: RunEvent) -> None:
        for q in self._subscribers:
            q.put_nowait(event)

    def close(self) -> None:
        self._closed = True
        for q in self._subscribers:
            q.put_nowait(None)
