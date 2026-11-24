"""Session state and the parent-linked message log.

A :class:`Session` is a live instance of an Agent configuration. Its message
log stores :class:`Turn` entries linked by ``parent_id`` so branches and
summaries can be reconstructed.
"""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Protocol

from loguru import logger

from agentbox_harness.spec import AgentSpec


@dataclass(frozen=True)
class Turn:
    """A single message-like entry in a session's message log."""

    id: str
    role: str
    content: str
    parent_id: str | None
    context_tokens: int | None = None
    created_at: datetime | None = None
    activity: dict | None = None
    attachments: list[dict] | None = None


class MessageLogStore(Protocol):
    """Persistence contract for a session's turn log."""

    async def append(self, turn: Turn) -> None: ...  # noqa: D102

    async def list_turns(self) -> list[Turn]: ...  # noqa: D102

    async def get(self, turn_id: str) -> Turn: ...  # noqa: D102

    async def set_parent(self, turn_id: str, parent_id: str) -> None: ...  # noqa: D102


class InMemoryMessageLogStore:
    """In-memory :class:`MessageLogStore` used for tests and local runs."""

    def __init__(self) -> None:  # noqa: D107
        self._turns: dict[str, Turn] = {}

    async def append(self, turn: Turn) -> None:
        """Store a turn, stamping ``created_at`` when it is unset."""
        if turn.created_at is None:
            turn = replace(turn, created_at=datetime.now(UTC))
        self._turns[turn.id] = turn

    async def list_turns(self) -> list[Turn]:
        """Return all stored turns in insertion order."""
        return list(self._turns.values())

    async def get(self, turn_id: str) -> Turn:
        """Return a stored turn by id.

        Raises:
            KeyError: If no turn with ``turn_id`` exists.
        """
        return self._turns[turn_id]

    async def set_parent(self, turn_id: str, parent_id: str) -> None:
        """Repoint a stored turn at a new parent."""
        turn = self._turns[turn_id]
        self._turns[turn_id] = replace(turn, parent_id=parent_id)


@dataclass
class Session:
    """A live instance of an Agent configuration with its message log.

    The session tracks ``head_id``, the newest turn on the active branch. Turns
    are linked by ``parent_id`` so history can be rebuilt from any head.
    """

    session_id: str
    project_root: str
    agent_spec: AgentSpec | None
    store: MessageLogStore
    head_id: str | None
    mode_name: str = "agent"
    extra_roots: list[str] = field(default_factory=list)
    plugin_roots: list[str] = field(default_factory=list)

    async def append(self, turn: Turn, parent_id: str | None) -> None:
        """Append a turn to the log and make it the active head.

        Args:
            turn: Turn to store.
            parent_id: Parent turn id, or ``None`` to start a new root.
        """
        turn = replace(turn, parent_id=parent_id)
        await self.store.append(turn)
        # The just-appended turn becomes the head of the active branch.
        self.head_id = turn.id
        logger.debug("session turn appended session={} role={}", self.session_id, turn.role)

    async def insert_summary(
        self,
        summary: Turn,
        cutoff_id: str,
        retained_first: Turn | None,
    ) -> None:
        """Insert a summary turn into the log at a branch cutoff.

        Args:
            summary: Summary turn to insert.
            cutoff_id: Turn id the summary replaces as the new parent.
            retained_first: First turn kept after the cutoff, reparented under
                the summary, or ``None`` when the summary becomes the head.
        """
        summary = replace(summary, parent_id=cutoff_id)
        await self.store.append(summary)
        if retained_first is not None:
            # Keep retained turns reachable by linking them under the summary.
            await self.store.set_parent(retained_first.id, summary.id)
        else:
            # With nothing retained, the summary is the active head.
            self.head_id = summary.id

    async def history(self) -> list[Turn]:
        """Return the active conversation branch from root to head.

        The store is a parent-linked log, so the head is walked backwards until a
        summary turn or a root turn is reached, then the chain is reversed into
        chronological order.
        """
        if self.head_id is None:
            return []
        chain: list[Turn] = []
        current = await self.store.get(self.head_id)
        while True:
            chain.append(current)
            # Stop at a summary turn, which collapses earlier history.
            # Also stop at a root turn, which has no parent to follow.
            if current.role == "summary" or current.parent_id is None:
                break
            current = await self.store.get(current.parent_id)
        return list(reversed(chain))
