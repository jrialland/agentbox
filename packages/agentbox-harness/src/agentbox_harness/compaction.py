"""Summarize old session turns when a run approaches the context window.

:class:`CompactionMiddleware` watches the latest reported context usage and,
once it crosses a configured ratio, replaces older turns with a summary turn
while retaining the newest turns on the active branch.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from loguru import logger
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model

from agentbox_harness.messages import turns_to_messages
from agentbox_harness.middleware import RunContext
from agentbox_harness.session import Turn

SUMMARY_SYSTEM_PROMPT = """You compress conversation history for an AI coding agent.
Produce a concise summary under these headings: Goal, Decisions, Work completed,
Files and commands, Current state, Open tasks. Preserve exact file paths, commands,
errors, identifiers, and user constraints. Do not invent details. Output only the
summary."""


@dataclass(frozen=True)
class CompactionConfig:
    """Thresholds controlling when and how aggressively history is compacted.

    ``ratio`` is the fraction of the model context window that triggers
    compaction, and ``keep_turns`` is the number of newest turns never
    summarized.
    """

    enabled: bool = True
    ratio: float = 0.8
    keep_turns: int = 4
    input_budget_tokens: int = 16_000
    max_summary_chars: int = 8_000


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _latest_usage(history: list[Turn]) -> Turn | None:
    for turn in reversed(history):
        if turn.role == "assistant" and turn.context_tokens is not None:
            return turn
    return None


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _summary_after(history: list[Turn], usage: Turn) -> bool:
    usage_time = _as_utc(usage.created_at)
    if usage_time is None:
        return False
    for turn in history:
        if turn.role != "summary":
            continue
        summary_time = _as_utc(turn.created_at)
        if summary_time is not None and summary_time > usage_time:
            return True
    return False


def _format_turn(turn: Turn) -> str:
    return f"[{turn.role}]\n{turn.content}"


class CompactionMiddleware:
    """Middleware that summarizes older turns to recover context budget.

    ``before_run`` compacts proactively when usage crosses the configured
    ratio; ``on_context_overflow`` compacts in response to a context-window
    error.
    """

    def __init__(self, config: CompactionConfig | None = None):
        self.config = config or CompactionConfig()

    async def before_run(self, ctx: RunContext) -> None:
        """Compact before a run when usage is near the context window.

        Compaction is skipped when disabled, when the model profile has no
        context window, when no assistant turn reports usage, or when a
        summary already postdates that usage.

        Args:
            ctx: Run context providing the session history and model.
        """
        if not self.config.enabled:
            return
        window = ctx.model.profile.get("context_window")
        if not window:
            return
        history = await ctx.session.history()
        usage = _latest_usage(history)
        if usage is None or usage.context_tokens is None:
            return
        if _summary_after(history, usage):
            return
        if usage.context_tokens < int(window * self.config.ratio):
            return
        await self.compact(ctx)

    async def on_context_overflow(
        self, ctx: RunContext
    ) -> list[ModelMessage] | None:
        """React to a context-window overflow by compacting history.

        Args:
            ctx: Run context providing the session history and model.

        Returns:
            Replacement model messages, or ``None`` when compaction was
            disabled or produced nothing.
        """
        if not self.config.enabled:
            return None
        return await self.compact(ctx)

    async def compact(self, ctx: RunContext) -> list[ModelMessage] | None:
        """Summarize older turns and insert a summary turn at the cutoff.

        The newest ``keep_turns`` turns are always retained. Older turns are
        selected in order until the summarization input budget is exhausted,
        so the cutoff is the last turn that fits. The summary replaces those
        turns on the active branch.

        Args:
            ctx: Run context providing the session history and model.

        Returns:
            Rebuilt model messages, or ``None`` when there is nothing to
            compact or summarization failed.
        """
        history = await ctx.session.history()
        keep = max(0, self.config.keep_turns)
        # Retain the newest turns; only older turns are summary candidates.
        candidates = history[:-keep] if keep else list(history)
        if not candidates:
            return None

        window = ctx.model.profile.get("context_window")
        budget = self.config.input_budget_tokens
        if window:
            budget = min(budget, max(1_000, window // 2))

        # Select candidates in order until the summarization budget is spent;
        # the last selected turn becomes the cutoff.
        selected: list[Turn] = []
        used = 0
        for turn in candidates:
            cost = _estimate_tokens(turn.content)
            if selected and used + cost > budget:
                break
            selected.append(turn)
            used += cost
        if not selected:
            return None

        cutoff = selected[-1]
        retained_first = history[len(selected)] if len(history) > len(selected) else None
        text = "\n\n".join(_format_turn(turn) for turn in selected)
        # Truncate oversized input so the summarizer stays within its budget.
        if len(text) > budget * 4:
            text = text[: budget * 4] + "\n\n[truncated]"

        summary = await self._summarize(ctx.model, text)
        if not summary:
            return None
        summary = summary[: self.config.max_summary_chars]
        summary_turn = Turn(
            id=uuid.uuid4().hex,
            role="summary",
            content=summary,
            parent_id=cutoff.id,
            created_at=datetime.now(UTC),
        )
        # Insert the summary at the cutoff; the first retained turn is
        # reparented under the summary so the branch stays reachable.
        await ctx.session.insert_summary(summary_turn, cutoff.id, retained_first)
        result = turns_to_messages(await ctx.session.history())
        ctx.message_history = result
        return result

    async def _summarize(self, model: Model, text: str) -> str | None:
        """Summarize ``text`` with the compaction system prompt.

        Returns ``None`` when the model returns no output or summarization
        raises; failures are logged rather than propagated.
        """
        try:
            agent = Agent(model, system_prompt=SUMMARY_SYSTEM_PROMPT)
            result = await agent.run(text)
            return str(result.output).strip() or None
        except Exception:
            logger.exception("compaction summarization failed")
            return None
