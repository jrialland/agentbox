import uuid

from loguru import logger
from sqlmodel import select

from agentbox_harness.session import Turn
from agentbox_models.tables.core import (
    MediaFile,
    SessionAttachment,
    TurnActivity,
    TurnAttachment,
    TurnRow,
    TurnToolActivity,
    utcnow,
)


async def _load_activity(session, turn_id: str) -> dict | None:
    row = await session.get(TurnActivity, turn_id)
    if row is None:
        return None
    tools = (
        await session.execute(
            select(TurnToolActivity)
            .where(TurnToolActivity.turn_id == turn_id)
            .order_by(TurnToolActivity.position)  # ty: ignore[invalid-argument-type]
        )
    ).scalars().all()
    error = None
    if row.error_code is not None or row.error_message is not None:
        error = {"code": row.error_code, "message": row.error_message}
    return {
        "status": row.status,
        "reasoning_ms": row.reasoning_ms,
        "reasoning_text": row.reasoning_text,
        "tools": [
            {
                "name": tool.name,
                "status": tool.status,
                "duration_ms": tool.duration_ms,
                "args": tool.args,
                "result": tool.result,
            }
            for tool in tools
        ],
        "error": error,
    }


async def _load_attachments(session, turn_id: str) -> list[dict] | None:
    rows = (
        await session.execute(
            select(TurnAttachment, SessionAttachment, MediaFile)
            .join(
                SessionAttachment,
                SessionAttachment.id == TurnAttachment.attachment_id,  # ty: ignore[invalid-argument-type]
            )
            .join(MediaFile, MediaFile.id == SessionAttachment.file_id)  # ty: ignore[invalid-argument-type]
            .where(TurnAttachment.turn_id == turn_id)
            .order_by(TurnAttachment.position)  # ty: ignore[invalid-argument-type]
        )
    ).all()
    if not rows:
        return None
    return [
        {
            "id": attachment.id,
            "filename": attachment.filename,
            "media_type": media.media_type,
        }
        for _link, attachment, media in rows
    ]


class DatabaseMessageLogStore:
    def __init__(self, session_factory, session_id: str):
        self._factory = session_factory
        self._session_id = session_id

    async def append(self, turn: Turn) -> None:
        async with self._factory() as s:
            s.add(
                TurnRow(
                    id=turn.id,
                    session_id=self._session_id,
                    role=turn.role,
                    content=turn.content,
                    parent_id=turn.parent_id,
                    context_tokens=turn.context_tokens,
                    created_at=turn.created_at or utcnow(),
                )
            )
            await s.flush()
            if turn.activity is not None:
                activity = turn.activity
                error = activity.get("error") or {}
                s.add(
                    TurnActivity(
                        turn_id=turn.id,
                        status=str(activity.get("status", "")),
                        reasoning_ms=int(activity.get("reasoning_ms") or 0),
                        reasoning_text=str(activity.get("reasoning_text") or ""),
                        error_code=error.get("code"),
                        error_message=error.get("message"),
                    )
                )
                for position, tool in enumerate(activity.get("tools") or []):
                    s.add(
                        TurnToolActivity(
                            id=uuid.uuid4().hex,
                            turn_id=turn.id,
                            position=position,
                            name=str(tool.get("name", "")),
                            status=str(tool.get("status", "")),
                            duration_ms=int(tool.get("duration_ms") or 0),
                            args=str(tool.get("args") or ""),
                            result=str(tool.get("result") or ""),
                        )
                    )
            for position, attachment in enumerate(turn.attachments or []):
                s.add(
                    TurnAttachment(
                        turn_id=turn.id,
                        attachment_id=attachment["id"],
                        position=position,
                    )
                )
            await s.commit()
            logger.debug("turn appended session={} role={}", self._session_id, turn.role)

    async def list_turns(self) -> list[Turn]:
        async with self._factory() as s:
            rows = (
                await s.execute(
                    select(TurnRow)
                    .where(TurnRow.session_id == self._session_id)
                    .order_by(TurnRow.created_at)  # ty: ignore[invalid-argument-type]
                )
            ).scalars().all()
            turns = []
            for row in rows:
                turns.append(
                    Turn(
                        id=row.id,
                        role=row.role,
                        content=row.content,
                        parent_id=row.parent_id,
                        context_tokens=row.context_tokens,
                        created_at=row.created_at,
                        activity=await _load_activity(s, row.id),
                        attachments=await _load_attachments(s, row.id),
                    )
                )
        return turns

    async def get(self, turn_id: str) -> Turn:
        async with self._factory() as s:
            row = (
                await s.execute(select(TurnRow).where(TurnRow.id == turn_id))
            ).scalars().first()
            if row is None:
                raise KeyError(turn_id)
            return Turn(
                id=row.id,
                role=row.role,
                content=row.content,
                parent_id=row.parent_id,
                context_tokens=row.context_tokens,
                created_at=row.created_at,
                activity=await _load_activity(s, row.id),
                attachments=await _load_attachments(s, row.id),
            )

    async def set_parent(self, turn_id: str, parent_id: str) -> None:
        async with self._factory() as s:
            row = await s.get(TurnRow, turn_id)
            if row is None:
                raise KeyError(turn_id)
            row.parent_id = parent_id
            s.add(row)
            await s.commit()
