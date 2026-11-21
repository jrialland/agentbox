from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Protocol

from loguru import logger

from agentbox_harness.spec import AgentSpec


@dataclass(frozen=True)
class Turn:
    id: str
    role: str
    content: str
    parent_id: str | None
    context_tokens: int | None = None
    created_at: datetime | None = None
    activity: dict | None = None
    attachments: list[dict] | None = None


class MessageLogStore(Protocol):
    async def append(self, turn: Turn) -> None: ...

    async def list_turns(self) -> list[Turn]: ...

    async def get(self, turn_id: str) -> Turn: ...

    async def set_parent(self, turn_id: str, parent_id: str) -> None: ...


class InMemoryMessageLogStore:
    def __init__(self) -> None:
        self._turns: dict[str, Turn] = {}

    async def append(self, turn: Turn) -> None:
        if turn.created_at is None:
            turn = replace(turn, created_at=datetime.now(UTC))
        self._turns[turn.id] = turn

    async def list_turns(self) -> list[Turn]:
        return list(self._turns.values())

    async def get(self, turn_id: str) -> Turn:
        return self._turns[turn_id]

    async def set_parent(self, turn_id: str, parent_id: str) -> None:
        turn = self._turns[turn_id]
        self._turns[turn_id] = replace(turn, parent_id=parent_id)


@dataclass
class Session:
    session_id: str
    project_root: str
    agent_spec: AgentSpec | None
    store: MessageLogStore
    head_id: str | None
    mode_name: str = "agent"
    extra_roots: list[str] = field(default_factory=list)

    async def append(self, turn: Turn, parent_id: str | None) -> None:
        turn = replace(turn, parent_id=parent_id)
        await self.store.append(turn)
        self.head_id = turn.id
        logger.debug("session turn appended session={} role={}", self.session_id, turn.role)

    async def insert_summary(
        self,
        summary: Turn,
        cutoff_id: str,
        retained_first: Turn | None,
    ) -> None:
        summary = replace(summary, parent_id=cutoff_id)
        await self.store.append(summary)
        if retained_first is not None:
            await self.store.set_parent(retained_first.id, summary.id)
        else:
            self.head_id = summary.id

    async def history(self) -> list[Turn]:
        if self.head_id is None:
            return []
        chain: list[Turn] = []
        current = await self.store.get(self.head_id)
        while True:
            chain.append(current)
            if current.role == "summary" or current.parent_id is None:
                break
            current = await self.store.get(current.parent_id)
        return list(reversed(chain))
