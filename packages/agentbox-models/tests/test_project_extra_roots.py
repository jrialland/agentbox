from sqlmodel import select

from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import Project


async def test_project_extra_roots_roundtrip():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    try:
        async with factory() as s:
            s.add(
                Project(
                    id="p1",
                    name="P",
                    path="/tmp/p",
                    owner_id="u1",
                    extra_roots=["/tmp/extra"],
                )
            )
            await s.commit()
        async with factory() as s:
            project = (
                await s.execute(select(Project).where(Project.id == "p1"))
            ).scalars().first()
        assert project is not None
        assert project.extra_roots == ["/tmp/extra"]
    finally:
        await engine.dispose()
