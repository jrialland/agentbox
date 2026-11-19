"""ACP (Agent Client Protocol) adapter for Agentbox.

Maps ACP prompt content and Pydantic AI stream events to ACP schema models.
The ACP agent + CLI are added below (Task 4).
"""

from __future__ import annotations

import base64

from acp import schema as s
from pydantic_ai.messages import (
    BinaryContent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    TextPartDelta,
    ThinkingPartDelta,
)


def prompt_parts(blocks) -> list:
    """Convert ACP ``ContentBlock``s to a ``prompt_override`` list (str / BinaryContent)."""
    parts: list = []
    for block in blocks:
        kind = getattr(block, "type", None)
        if kind == "text":
            parts.append(block.text)
        elif kind == "resource_link":
            mime = f" ({block.mime_type})" if getattr(block, "mime_type", None) else ""
            parts.append(f"[resource: {block.name} {block.uri}{mime}]")
        elif kind in ("image", "audio"):
            parts.append(
                BinaryContent(data=base64.b64decode(block.data), media_type=block.mime_type)
            )
        elif kind == "resource":
            resource = block.resource
            text = getattr(resource, "text", None)
            blob = getattr(resource, "blob", None)
            if text is not None:
                parts.append(f"[resource {resource.uri}]\n{text}")
            elif blob is not None:
                media = (
                    getattr(resource, "mime_type", None) or "application/octet-stream"
                )
                parts.append(
                    BinaryContent(
                        data=base64.b64decode(blob),
                        media_type=media,
                    )
                )
            else:
                raise ValueError("invalid embedded resource")
        else:
            raise ValueError(f"unsupported content block: {kind}")
    return parts


def update_for_event(event):
    """Map a Pydantic AI stream event to an ACP ``session/update`` payload (or None)."""
    if isinstance(event, PartDeltaEvent):
        delta = event.delta
        text = getattr(delta, "content_delta", None)
        if isinstance(delta, TextPartDelta) and text:
            return s.AgentMessageChunk(content=s.TextContentBlock(text=text))
        if isinstance(delta, ThinkingPartDelta) and text:
            return s.AgentThoughtChunk(content=s.TextContentBlock(text=text))
        return None
    if isinstance(event, FunctionToolCallEvent):
        part = event.part
        return s.ToolCallStart(
            tool_call_id=part.tool_call_id,
            title=part.tool_name,
            name=part.tool_name,
            kind="other",
            status="pending",
        )
    if isinstance(event, FunctionToolResultEvent):
        part = event.part
        text = event.content if event.content is not None else str(part.content)
        return s.ToolCallProgress(
            tool_call_id=part.tool_call_id,
            status="completed",
            content=[s.ContentToolCallContent(content=s.TextContentBlock(text=text))],
        )
    return None
