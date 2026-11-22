import uuid

from sqlalchemy import delete
from sqlmodel import select

from agentbox_models.tables.core import ProjectRoot


async def load_extra_roots(session, project_id: str) -> list[str]:
    rows = (
        await session.execute(
            select(ProjectRoot)
            .where(ProjectRoot.project_id == project_id)
            .order_by(ProjectRoot.position)
        )
    ).scalars().all()
    return [row.path for row in rows]


async def replace_extra_roots(session, project_id: str, paths: list[str]) -> None:
    await session.execute(
        delete(ProjectRoot).where(ProjectRoot.project_id == project_id)
    )
    for position, path in enumerate(paths):
        session.add(
            ProjectRoot(
                id=uuid.uuid4().hex,
                project_id=project_id,
                position=position,
                path=path,
            )
        )
