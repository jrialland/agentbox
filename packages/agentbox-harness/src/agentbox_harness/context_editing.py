from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

from loguru import logger
from pydantic_ai import RunContext
from pydantic_ai.messages import (
    BinaryContent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

CLEARED_MARKER = "context_editing"


@dataclass(frozen=True)
class ContextEditingConfig:
    enabled: bool = True
    trigger_tokens: int = 100_000
    trigger_ratio: float = 0.8
    target_ratio: float = 0.6
    keep_tool_results: int = 3
    keep_recent_messages: int = 6
    clear_tool_inputs: bool = False
    clear_binary: bool = True
    exclude_tools: tuple[str, ...] = ()
    placeholder: str = (
        "[tool result cleared to save context; re-run the tool if needed]"
    )
    binary_placeholder: str = "[attachment omitted to save context]"


@dataclass(frozen=True)
class ContextEditingStats:
    triggered: bool
    before_tokens: int
    after_tokens: int
    trigger_tokens: int
    cleared_tool_results: int = 0
    cleared_tool_inputs: int = 0
    cleared_binary_items: int = 0


def _text_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _binary_tokens(data: bytes) -> int:
    return max(1_000, len(data) // 4)


def _content_tokens(content: Any) -> int:
    if content is None:
        return 1
    if isinstance(content, str):
        return _text_tokens(content)
    if isinstance(content, BinaryContent):
        return _binary_tokens(content.data)
    if isinstance(content, bytes):
        return _binary_tokens(content)
    if isinstance(content, (list, tuple)):
        return sum(_content_tokens(item) for item in content) or 1
    if isinstance(content, dict):
        return _text_tokens(json.dumps(content, default=str))
    return _text_tokens(str(content))


def _part_tokens(part: Any) -> int:
    if isinstance(part, ToolCallPart):
        return _content_tokens(part.args)
    content = getattr(part, "content", None)
    if content is not None:
        return _content_tokens(content)
    return 4


def estimate_messages_tokens(messages: list[ModelMessage]) -> int:
    total = 0
    for message in messages:
        total += 4
        if isinstance(message, (ModelRequest, ModelResponse)):
            total += sum(_part_tokens(part) for part in message.parts)
    return total


def _is_cleared(part: ToolReturnPart) -> bool:
    metadata = part.metadata
    if not isinstance(metadata, dict):
        return False
    marker = metadata.get(CLEARED_MARKER)
    return isinstance(marker, dict) and bool(marker.get("cleared"))


def _clear_metadata(part: ToolReturnPart, original_tokens: int) -> dict:
    metadata = part.metadata if isinstance(part.metadata, dict) else {}
    return {
        **metadata,
        CLEARED_MARKER: {
            "cleared": True,
            "strategy": "clear_tool_uses",
            "original_tokens": original_tokens,
        },
    }


def _cleared_tool_return(
    part: ToolReturnPart, config: ContextEditingConfig, original_tokens: int
) -> ToolReturnPart:
    return ToolReturnPart(
        tool_name=part.tool_name,
        content=config.placeholder,
        tool_call_id=part.tool_call_id,
        tool_kind=None,
        metadata=_clear_metadata(part, original_tokens),
        timestamp=part.timestamp,
        outcome=part.outcome,
    )


def _cleared_tool_call(part: ToolCallPart) -> ToolCallPart:
    return ToolCallPart(
        tool_name=part.tool_name,
        args={},
        tool_call_id=part.tool_call_id,
        tool_kind=None,
        id=part.id,
        provider_name=part.provider_name,
        provider_details=part.provider_details,
    )


def _tool_call_index(
    messages: list[ModelMessage],
) -> dict[str, tuple[int, int]]:
    index: dict[str, tuple[int, int]] = {}
    for message_index, message in enumerate(messages):
        if not isinstance(message, ModelResponse):
            continue
        for part_index, part in enumerate(message.parts):
            if isinstance(part, ToolCallPart):
                index[part.tool_call_id] = (message_index, part_index)
    return index


def _clear_tool_input(
    messages: list[ModelMessage],
    call_index: dict[str, tuple[int, int]],
    tool_call_id: str,
) -> bool:
    location = call_index.get(tool_call_id)
    if location is None:
        return False
    message_index, part_index = location
    message = messages[message_index]
    if not isinstance(message, ModelResponse):
        return False
    parts = list(message.parts)
    part = parts[part_index]
    if not isinstance(part, ToolCallPart) or part.args in (None, {}):
        return False
    parts[part_index] = _cleared_tool_call(part)
    messages[message_index] = replace(message, parts=parts)
    return True


def _clear_binary_in_user_prompts(
    messages: list[ModelMessage],
    config: ContextEditingConfig,
    recent_start: int,
    target: int,
) -> tuple[int, int]:
    cleared = 0
    after = estimate_messages_tokens(messages)
    for message_index in range(recent_start):
        if after <= target:
            break
        message = messages[message_index]
        if not isinstance(message, ModelRequest):
            continue
        parts = list(message.parts)
        changed = False
        for part_index, part in enumerate(parts):
            if not isinstance(part, UserPromptPart):
                continue
            content = part.content
            if isinstance(content, str):
                continue
            if not isinstance(content, (list, tuple)):
                continue
            new_content = []
            part_cleared = 0
            for item in content:
                if isinstance(item, BinaryContent):
                    new_content.append(config.binary_placeholder)
                    part_cleared += 1
                else:
                    new_content.append(item)
            if part_cleared:
                parts[part_index] = UserPromptPart(
                    content=new_content, timestamp=part.timestamp
                )
                cleared += part_cleared
                changed = True
        if changed:
            messages[message_index] = replace(message, parts=parts)
            after = estimate_messages_tokens(messages)
    return cleared, after


def apply_context_edits(
    messages: list[ModelMessage],
    *,
    trigger_tokens: int,
    config: ContextEditingConfig,
) -> tuple[list[ModelMessage], ContextEditingStats]:
    before = estimate_messages_tokens(messages)
    if before <= trigger_tokens:
        return messages, ContextEditingStats(
            triggered=False,
            before_tokens=before,
            after_tokens=before,
            trigger_tokens=trigger_tokens,
        )

    edited = list(messages)
    recent_start = max(0, len(edited) - config.keep_recent_messages)
    excluded = set(config.exclude_tools)
    candidates: list[tuple[int, int, ToolReturnPart]] = []
    for message_index, message in enumerate(edited):
        if message_index >= recent_start or not isinstance(message, ModelRequest):
            continue
        for part_index, part in enumerate(message.parts):
            if not isinstance(part, ToolReturnPart):
                continue
            if part.tool_name in excluded or _is_cleared(part):
                continue
            candidates.append((message_index, part_index, part))

    keep = max(0, config.keep_tool_results)
    clearable = candidates[:-keep] if keep else candidates
    target = max(0, int(trigger_tokens * min(config.target_ratio, 1.0)))
    call_index = _tool_call_index(edited)
    cleared_results = 0
    cleared_inputs = 0
    after = before
    for message_index, part_index, part in clearable:
        if after <= target:
            break
        message = edited[message_index]
        if not isinstance(message, ModelRequest):
            continue
        parts = list(message.parts)
        original_tokens = _part_tokens(part)
        parts[part_index] = _cleared_tool_return(part, config, original_tokens)
        edited[message_index] = replace(message, parts=parts)
        cleared_results += 1
        if config.clear_tool_inputs and _clear_tool_input(
            edited, call_index, part.tool_call_id
        ):
            cleared_inputs += 1
        after = estimate_messages_tokens(edited)

    cleared_binary = 0
    if config.clear_binary and after > target:
        cleared_binary, after = _clear_binary_in_user_prompts(
            edited, config, recent_start, target
        )

    stats = ContextEditingStats(
        triggered=True,
        before_tokens=before,
        after_tokens=after,
        trigger_tokens=trigger_tokens,
        cleared_tool_results=cleared_results,
        cleared_tool_inputs=cleared_inputs,
        cleared_binary_items=cleared_binary,
    )
    return edited, stats


def make_context_editing_processor(config: ContextEditingConfig):
    def process(
        ctx: RunContext[Any], messages: list[ModelMessage]
    ) -> list[ModelMessage]:
        trigger = max(0, config.trigger_tokens)
        profile = getattr(ctx.model, "profile", None)
        if isinstance(profile, dict):
            window = profile.get("context_window")
            if window:
                trigger = min(
                    trigger,
                    int(window * min(max(config.trigger_ratio, 0.05), 1.0)),
                )
        try:
            edited, stats = apply_context_edits(
                messages, trigger_tokens=trigger, config=config
            )
        except Exception:
            logger.exception("context editing failed; keeping history unchanged")
            return messages
        if stats.triggered:
            logger.info(
                "context editing trigger={} before={} after={} "
                "tool_results={} tool_inputs={} binary={}",
                stats.trigger_tokens,
                stats.before_tokens,
                stats.after_tokens,
                stats.cleared_tool_results,
                stats.cleared_tool_inputs,
                stats.cleared_binary_items,
            )
        return edited

    return process
