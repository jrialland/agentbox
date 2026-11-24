"""Read and replace the extra project roots used for workspace resolution.

Roots are stored per project with a dense position column. Both helpers run on a
caller-owned session and never commit, so the caller owns the transaction.
"""

import uuid

from sqlalchemy import delete
from sqlmodel import select

from agentbox_models.tables.core import ProjectRoot


async def load_extra_roots(session, project_id: str) -> list[str]:
    """Return a project's extra roots ordered by position.

    The primary project root lives on the project row and is not included.

    Args:
        session: Caller-owned session; the caller controls the transaction.
        project_id: Project whose extra roots should be listed.

    Returns:
        Root paths in stored position order, or an empty list when none exist.
    """
    rows = (
        await session.execute(
            select(ProjectRoot)
            .where(ProjectRoot.project_id == project_id)
            .order_by(ProjectRoot.position)  # ty: ignore[invalid-argument-type]
        )
    ).scalars().all()
    return [row.path for row in rows]


async def replace_extra_roots(session, project_id: str, paths: list[str]) -> None:
    """Replace a project's extra roots with ``paths``.

    Existing rows are deleted before the new set is inserted, so removed roots do
    not linger. Duplicate paths are stored as given, and positions follow the
    caller's order so resolution can replay it.

    Args:
        session: Caller-owned session; the caller must commit.
        project_id: Project whose extra roots should be rewritten.
        paths: Root paths in the desired resolution order.
    """
    # Delete then reinsert keeps positions dense and avoids reconciling rows.
    await session.execute(
        delete(ProjectRoot).where(ProjectRoot.project_id == project_id)  # ty: ignore[invalid-argument-type]
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
