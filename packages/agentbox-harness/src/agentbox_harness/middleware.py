from dataclasses import dataclass, field
from typing import Protocol

from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model

from agentbox_harness.errors import RunOutcome
from agentbox_harness.events import EventBus
from agentbox_harness.session import Session


@dataclass
class RunContext:
    session: Session
    model: Model
    bus: EventBus
    prompt: str
    prompt_override: list | None = None
    message_history: list[ModelMessage] = field(default_factory=list)
    outcome: RunOutcome | None = None


class SessionReminder(Protocol):
    async def reminder(self, session: Session) -> str | None: ...


class RunMiddleware(Protocol):
    async def before_run(self, ctx: RunContext) -> None: ...

    async def on_context_overflow(
        self, ctx: RunContext
    ) -> list[ModelMessage] | None: ...


class MiddlewarePipeline:
    def __init__(self, middleware: list[RunMiddleware] | None = None):
        self._middleware = list(middleware or [])

    async def prepare(self, ctx: RunContext) -> None:
        for item in self._middleware:
            await item.before_run(ctx)

    async def recover(self, ctx: RunContext) -> list[ModelMessage] | None:
        for item in self._middleware:
            history = await item.on_context_overflow(ctx)
            if history is not None:
                ctx.message_history = history
                return history
        return None
