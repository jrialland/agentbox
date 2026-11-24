"""Middleware hooks that observe and adjust a run before it executes."""

from dataclasses import dataclass, field
from typing import Protocol

from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model

from agentbox_harness.errors import RunOutcome
from agentbox_harness.events import EventBus
from agentbox_harness.session import Session


@dataclass
class RunContext:
    """Mutable state shared with middleware during a single run."""

    session: Session
    model: Model
    bus: EventBus
    prompt: str
    prompt_override: list | None = None
    message_history: list[ModelMessage] = field(default_factory=list)
    outcome: RunOutcome | None = None


class SessionReminder(Protocol):
    """Source of optional reminders injected into a session prompt."""

    async def reminder(self, session: Session) -> str | None: ...  # noqa: D102


class RunMiddleware(Protocol):
    """Hooks a middleware implementation can provide around a run."""

    async def before_run(self, ctx: RunContext) -> None: ...  # noqa: D102

    async def on_context_overflow(  # noqa: D102
        self, ctx: RunContext
    ) -> list[ModelMessage] | None: ...


class MiddlewarePipeline:
    """Run an ordered list of middleware hooks.

    ``prepare`` calls every middleware's ``before_run``; ``recover`` asks them
    in order for replacement history after a context overflow.
    """

    def __init__(self, middleware: list[RunMiddleware] | None = None):  # noqa: D107
        self._middleware = list(middleware or [])

    async def prepare(self, ctx: RunContext) -> None:
        """Run ``before_run`` on every middleware in registration order."""
        for item in self._middleware:
            await item.before_run(ctx)

    async def recover(self, ctx: RunContext) -> list[ModelMessage] | None:
        """Return replacement history from the first middleware that recovers.

        The returned history is also stored on ``ctx`` so later stages see it.

        Args:
            ctx: Run context to update when a middleware returns history.

        Returns:
            Replacement message history, or ``None`` when nothing recovered.
        """
        for item in self._middleware:
            history = await item.on_context_overflow(ctx)
            if history is not None:
                ctx.message_history = history
                return history
        return None
