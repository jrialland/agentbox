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


@dataclass
class ToolActivity:
    name: str
    started_at: float
    status: str = "success"
    ended_at: float | None = None


@dataclass
class RunActivityCollector:
    started_at: float = field(default_factory=time.monotonic)
    reasoning_started_at: float | None = None
    reasoning_ms: int = 0
    tools: dict[str, ToolActivity] = field(default_factory=dict)
    text: str = ""

    def observe(self, event: object) -> None:
        now = time.monotonic()
        if isinstance(event, PartStartEvent) and isinstance(event.part, ThinkingPart):
            if self.reasoning_started_at is None:
                self.reasoning_started_at = now
        if isinstance(event, PartDeltaEvent) and isinstance(
            event.delta, ThinkingPartDelta
        ):
            if self.reasoning_started_at is None:
                self.reasoning_started_at = now
        if isinstance(event, PartEndEvent) and isinstance(event.part, ThinkingPart):
            if self.reasoning_started_at is not None:
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
            )
        if isinstance(event, FunctionToolResultEvent):
            tool = self.tools.get(event.tool_call_id)
            if tool is not None:
                tool.ended_at = now
                tool.status = (
                    "success" if event.part.outcome == "success" else "error"
                )

    def summary(self, status: str, error: dict | None = None) -> dict:
        reasoning_ms = self.reasoning_ms
        if self.reasoning_started_at is not None:
            reasoning_ms += int(
                (time.monotonic() - self.reasoning_started_at) * 1000
            )
        return {
            "status": status,
            "reasoning_ms": reasoning_ms,
            "tools": [
                {
                    "name": tool.name,
                    "status": tool.status,
                    "duration_ms": int(
                        ((tool.ended_at or time.monotonic()) - tool.started_at)
                        * 1000
                    ),
                }
                for tool in self.tools.values()
            ],
            "error": error,
        }
