from loguru import logger
from sqlmodel import select

from agentbox_harness.session import Turn
from agentbox_models.tables.core import TurnRow, utcnow


class SQLiteMessageLogStore:
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
                    activity=turn.activity,
                    attachments=turn.attachments,
                )
            )
            await s.commit()
            logger.debug("turn appended session={} role={}", self._session_id, turn.role)

    async def list_turns(self) -> list[Turn]:
        async with self._factory() as s:
            rows = (
                await s.execute(
                    select(TurnRow).where(TurnRow.session_id == self._session_id)
                )
            ).scalars().all()
        return [
            Turn(
                id=r.id,
                role=r.role,
                content=r.content,
                parent_id=r.parent_id,
                context_tokens=r.context_tokens,
                created_at=r.created_at,
                activity=r.activity,
                attachments=r.attachments,
            )
            for r in rows
        ]

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
            activity=row.activity,
            attachments=row.attachments,
        )

    async def set_parent(self, turn_id: str, parent_id: str) -> None:
        async with self._factory() as s:
            row = await s.get(TurnRow, turn_id)
            if row is None:
                raise KeyError(turn_id)
            row.parent_id = parent_id
            s.add(row)
            await s.commit()
