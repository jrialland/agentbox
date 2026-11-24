"""Aggregate harness events into a per-run activity summary.

The collector consumes model part and tool events as they stream, tracking
reasoning time/text, emitted text, and per-tool status. Durations are measured
with :func:`time.monotonic` clocks, so they are suitable for elapsed-time
reporting rather than wall-clock timestamps.
"""

import time
from dataclasses import dataclass, field

from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
)

_MAX_ACTIVITY_TEXT = 4_000


def _preview(value: object) -> str:
    """Render a truncated string preview for activity reporting."""
    text = value if isinstance(value, str) else str(value)
    return text[:_MAX_ACTIVITY_TEXT]


@dataclass
class ToolActivity:
    """Accumulated timing and result for a single tool call."""

    name: str
    started_at: float
    status: str = "success"
    ended_at: float | None = None
    args: str = ""
    result: str = ""


@dataclass
class RunActivityCollector:
    """Accumulate streaming model and tool events into a run summary.

    Events are expected to arrive in emission order. Reasoning time is the sum
    of completed thinking-part intervals plus any still-open interval that
    :meth:`summary` closes out.
    """

    started_at: float = field(default_factory=time.monotonic)
    reasoning_started_at: float | None = None
    reasoning_ms: int = 0
    reasoning_text: str = ""
    tools: dict[str, ToolActivity] = field(default_factory=dict)
    text: str = ""

    def observe(self, event: object) -> None:
        """Record one streaming event into the accumulator.

        Part start/delta/end events extend reasoning or text; tool call events
        open a :class:`ToolActivity` and matching result events close it with a
        status. Unknown events are ignored.

        Args:
            event: A harness or pydantic-ai streaming event.
        """
        now = time.monotonic()
        if (
            isinstance(event, PartStartEvent)
            and isinstance(event.part, ThinkingPart)
        ):
            if self.reasoning_started_at is None:
                self.reasoning_started_at = now
            self.reasoning_text = _preview(self.reasoning_text + event.part.content)
        if (
            isinstance(event, PartDeltaEvent)
            and isinstance(event.delta, ThinkingPartDelta)
        ):
            if self.reasoning_started_at is None:
                self.reasoning_started_at = now
            self.reasoning_text = _preview(
                self.reasoning_text + (event.delta.content_delta or "")
            )
        if (
            isinstance(event, PartEndEvent)
            and isinstance(event.part, ThinkingPart)
            and self.reasoning_started_at is not None
        ):
            self.reasoning_ms += int((now - self.reasoning_started_at) * 1000)
            self.reasoning_started_at = None
        if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
            self.text += event.part.content
        if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
            self.text += event.delta.content_delta
        if isinstance(event, FunctionToolCallEvent):
            self.tools[event.tool_call_id] = ToolActivity(
                name=event.part.tool_name,
                started_at=now,
                args=_preview(event.part.args_as_json_str()),
            )
        if isinstance(event, FunctionToolResultEvent):
            tool = self.tools.get(event.tool_call_id)
            if tool is not None:
                tool.ended_at = now
                tool.status = (
                    "success" if event.part.outcome == "success" else "error"
                )
                tool.result = _preview(event.part.content)

    def summary(self, status: str, error: dict | None = None) -> dict:
        """Return the accumulated activity as a serializable summary.

        Any reasoning interval still open is counted up to the moment this is
        called, so the summary is stable for a finished run.

        Args:
            status: Terminal run status to report.
            error: Optional structured error details for failed runs.

        Returns:
            A dict with reasoning, tool, and error details.
        """
        reasoning_ms = self.reasoning_ms
        if self.reasoning_started_at is not None:
            reasoning_ms += int(
                (time.monotonic() - self.reasoning_started_at) * 1000
            )
        return {
            "status": status,
            "reasoning_ms": reasoning_ms,
            "reasoning_text": self.reasoning_text,
            "tools": [
                {
                    "name": tool.name,
                    "status": tool.status,
                    "duration_ms": int(
                        ((tool.ended_at or time.monotonic()) - tool.started_at)
                        * 1000
                    ),
                    "args": tool.args,
                    "result": tool.result,
                }
                for tool in self.tools.values()
            ],
            "error": error,
        }

