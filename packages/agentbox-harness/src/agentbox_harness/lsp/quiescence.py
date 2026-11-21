import asyncio
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class ServerStatusTracker:
    health: str | None = None
    quiescent: bool | None = None
    seq: int = 0
    busy_seq: int = 0
    waiters: set[asyncio.Event] = field(default_factory=set)

    def client_capabilities(self) -> dict:
        return {"experimental": {"serverStatusNotification": True}}

    def handle(self, params: dict) -> None:
        self.health = params.get("health")
        self.quiescent = bool(params.get("quiescent"))
        self.seq += 1
        if self.quiescent is False:
            self.busy_seq += 1
        logger.debug(
            "lsp server status health={} quiescent={}",
            self.health,
            self.quiescent,
        )
        if self.health not in (None, "ok"):
            logger.warning(
                "lsp server health={} message={}",
                self.health,
                params.get("message"),
            )
        for waiter in self.waiters:
            waiter.set()
