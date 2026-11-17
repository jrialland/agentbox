from sqlmodel import select

from agentbox_harness.session import Turn
from agentbox_models.tables.core import TurnRow


class SQLiteMessageLogStore:
    def __init__(self, session, session_id: str):
        self._session = session
        self._session_id = session_id

    async def append(self, turn: Turn) -> None:
        self._session.add(
            TurnRow(
                id=turn.id,
                session_id=self._session_id,
                role=turn.role,
                content=turn.content,
                parent_id=turn.parent_id,
            )
        )
        await self._session.commit()

    async def list_turns(self) -> list[Turn]:
        rows = (
            await self._session.execute(
                select(TurnRow).where(TurnRow.session_id == self._session_id)
            )
        ).scalars().all()
        return [
            Turn(id=r.id, role=r.role, content=r.content, parent_id=r.parent_id)
            for r in rows
        ]

    async def get(self, turn_id: str) -> Turn:
        row = (
            await self._session.execute(
                select(TurnRow).where(TurnRow.id == turn_id)
            )
        ).scalars().first()
        if row is None:
            raise KeyError(turn_id)
        return Turn(
            id=row.id, role=row.role, content=row.content, parent_id=row.parent_id
        )
