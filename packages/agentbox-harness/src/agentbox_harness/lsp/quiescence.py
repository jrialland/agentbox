"""Track experimental LSP server-status notifications for quiescence waits.

Servers that opt into ``serverStatusNotification`` report whether they are busy
analyzing. The tracker turns those notifications into sequence counters so
diagnostic waits can tell new work apart from stale results.
"""

import asyncio
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class ServerStatusTracker:
    """Mutable snapshot of a server's reported health and quiescence state.

    Attributes:
        health: Last reported health string, or ``None`` before the first
            notification.
        quiescent: Last reported quiescence flag, or ``None`` if unknown.
        seq: Monotonic count of received status notifications.
        busy_seq: Count of notifications that reported ``quiescent is False``.
        waiters: Events woken whenever a new status notification arrives.
    """

    health: str | None = None
    quiescent: bool | None = None
    seq: int = 0
    busy_seq: int = 0
    waiters: set[asyncio.Event] = field(default_factory=set)

    def client_capabilities(self) -> dict:
        """Return the client capabilities that request server-status events."""
        return {"experimental": {"serverStatusNotification": True}}

    def handle(self, params: dict) -> None:
        """Record a server-status notification and wake all waiters.

        Args:
            params: Notification parameters containing ``health`` and
                ``quiescent``, plus an optional ``message`` for unhealthy
                servers.
        """
        self.health = params.get("health")
        self.quiescent = bool(params.get("quiescent"))
        self.seq += 1
        if self.quiescent is False:
            # Increment busy_seq for each busy (quiescent is False)
            # notification so a wait can detect activity after its baseline.
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
