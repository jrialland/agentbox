"""Session-scoped TODO/plan tools backed by ``PlanItem`` rows.

Each tool mutates or reads plan items for a single session, keeping persisted
``position`` values contiguous and rejecting invalid transitions with
``ModelRetry`` so the model can correct itself.
"""

import uuid
from collections.abc import Callable

from pydantic_ai import ModelRetry
from sqlmodel import select

from agentbox_models.tables.core import PlanItem, utcnow

PLAN_TOOL_NAMES = (
    "todo_add",
    "todo_update",
    "todo_complete",
    "todo_remove",
    "todo_reorder",
    "todo_list",
    "todo_clear",
)
STATUSES = {"pending", "in_progress", "completed"}
MAX_CONTENT = 500
MARKS = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}


def make_plan_tools(factory, session_id: str) -> dict[str, Callable]:
    """Build the TODO tool functions bound to one session.

    Args:
        factory: Async session factory used for each tool call.
        session_id: Session whose plan items the tools read and mutate.

    Returns:
        Mapping of tool name to its async implementation.
    """

    async def _load(s):
        # Position is the persisted ordering; ties are not expected because
        # every mutation rewrites positions contiguously.
        return (
            await s.execute(
                select(PlanItem)
                .where(PlanItem.session_id == session_id)
                .order_by(PlanItem.position)  # ty: ignore[invalid-argument-type]
            )
        ).scalars().all()

    def _content(value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ModelRetry("TODO content must not be empty.")
        if len(text) > MAX_CONTENT:
            raise ModelRetry(f"TODO content must be at most {MAX_CONTENT} characters.")
        return text

    async def _new_id(s) -> str:
        while True:
            candidate = uuid.uuid4().hex[:8]
            if await s.get(PlanItem, candidate) is None:
                return candidate

    async def _get(s, item_id: str) -> PlanItem:
        item = await s.get(PlanItem, item_id)
        # Scope lookups to this session so a model cannot mutate another
        # session's plan by guessing an id.
        if item is None or item.session_id != session_id:
            raise ModelRetry(f"Unknown TODO id: {item_id}")
        return item

    async def todo_add(content: str) -> str:
        text = _content(content)
        async with factory() as s:
            items = await _load(s)
            # Append after the current tail so existing positions stay stable.
            position = max((item.position for item in items), default=-1) + 1
            item = PlanItem(
                id=await _new_id(s),
                session_id=session_id,
                position=position,
                content=text,
            )
            s.add(item)
            await s.commit()
        return f"Added {item.id}: {text}"

    async def todo_update(
        item_id: str, content: str | None = None, status: str | None = None
    ) -> str:
        if content is None and status is None:
            raise ModelRetry("Provide content and/or status.")
        if status is not None and status not in STATUSES:
            raise ModelRetry(f"Invalid status: {status}")
        async with factory() as s:
            item = await _get(s, item_id)
            if content is not None:
                item.content = _content(content)
            if status is not None:
                item.status = status
            item.updated_at = utcnow()
            s.add(item)
            await s.commit()
        return f"Updated {item_id}"

    async def todo_complete(item_id: str) -> str:
        async with factory() as s:
            item = await _get(s, item_id)
            item.status = "completed"
            item.updated_at = utcnow()
            s.add(item)
            await s.commit()
        return f"Completed {item_id}"

    async def todo_remove(item_id: str) -> str:
        async with factory() as s:
            item = await _get(s, item_id)
            await s.delete(item)
            await s.flush()
            # Deleting leaves a gap; renumber the survivors contiguously.
            remaining = await _load(s)
            for position, entry in enumerate(remaining):
                entry.position = position
                s.add(entry)
            await s.commit()
        return f"Removed {item_id}"

    async def todo_reorder(item_ids: list[str]) -> str:
        if len(set(item_ids)) != len(item_ids):
            raise ModelRetry("TODO reorder list contains duplicates.")
        async with factory() as s:
            items = await _load(s)
            # Require a full permutation so no item silently drops out.
            if {item.id for item in items} != set(item_ids):
                raise ModelRetry(
                    "TODO reorder must include every current id exactly once."
                )
            by_id = {item.id: item for item in items}
            for position, item_id in enumerate(item_ids):
                entry = by_id[item_id]
                entry.position = position
                s.add(entry)
            await s.commit()
        return f"Reordered {len(item_ids)} items"

    async def todo_list() -> str:
        async with factory() as s:
            items = await _load(s)
        if not items:
            return "TODO list is empty."
        lines = [f"TODO list ({len(items)} items):"]
        lines.extend(
            f"{MARKS.get(item.status, '[ ]')} #{item.position} {item.id} {item.content}"
            for item in items
        )
        return "\n".join(lines)

    async def todo_clear() -> str:
        async with factory() as s:
            for item in await _load(s):
                await s.delete(item)
            await s.commit()
        return "TODO list cleared"

    return {
        "todo_add": todo_add,
        "todo_update": todo_update,
        "todo_complete": todo_complete,
        "todo_remove": todo_remove,
        "todo_reorder": todo_reorder,
        "todo_list": todo_list,
        "todo_clear": todo_clear,
    }
