from dataclasses import dataclass
from typing import Protocol

from agentbox_harness.spec import AgentSpec


@dataclass(frozen=True)
class Turn:
    id: str
    role: str
    content: str
    parent_id: str | None


class MessageLogStore(Protocol):
    def append(self, turn: Turn) -> None: ...

    def list_turns(self) -> list[Turn]: ...

    def get(self, turn_id: str) -> Turn: ...


class InMemoryMessageLogStore:
    def __init__(self) -> None:
        self._turns: dict[str, Turn] = {}

    def append(self, turn: Turn) -> None:
        self._turns[turn.id] = turn

    def list_turns(self) -> list[Turn]:
        return list(self._turns.values())

    def get(self, turn_id: str) -> Turn:
        return self._turns[turn_id]


@dataclass
class Session:
    session_id: str
    project_root: str
    agent_spec: AgentSpec | None
    store: MessageLogStore
    head_id: str | None

    def append(self, turn: Turn, parent_id: str | None) -> None:
        self.store.append(turn)
        self.head_id = turn.id

    def history(self) -> list[Turn]:
        if self.head_id is None:
            return []
        chain: list[Turn] = []
        current = self.store.get(self.head_id)
        while True:
            chain.append(current)
            if current.parent_id is None:
                break
            current = self.store.get(current.parent_id)
        return list(reversed(chain))
