import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel

from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.repos.project_roots import load_extra_roots, replace_extra_roots
from agentbox_models.tables.auth import User
from agentbox_models.tables.core import (
    Agent,
    Model,
    Project,
    Provider,
    SessionRow,
    TurnRow,
)


async def _reset(engine):
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)


@pytest.mark.timeout(180)
async def test_vendor_roundtrip_and_cascade(db_url):
    engine, factory = create_engine_and_sessionmaker(db_url)
    await init_db(engine)
    await _reset(engine)
    suffix = uuid.uuid4().hex[:8]
    long_text = ("é" * 300) + ("x" * 300)

    async with factory() as s:
        s.add(
            User(
                id=f"u{suffix}",
                username=f"u{suffix}",
                email="e@x",
                password_hash="h",
            )
        )
        s.add(Provider(id=f"p{suffix}", name="test", kind="generic"))
        await s.commit()
    async with factory() as s:
        s.add(Model(id=f"m{suffix}", provider_id=f"p{suffix}", name="test-model"))
        await s.commit()
    async with factory() as s:
        s.add(
            Agent(
                id=f"a{suffix}",
                name=f"agent-{suffix}",
                description=long_text,
                instructions=long_text,
                model_id=f"m{suffix}",
                created_by=f"u{suffix}",
            )
        )
        s.add(
            Project(
                id=f"pr{suffix}",
                name="p",
                path="/tmp/" + long_text,
                owner_id=f"u{suffix}",
            )
        )
        await s.commit()
    async with factory() as s:
        s.add(
            SessionRow(
                id=f"s{suffix}",
                project_id=f"pr{suffix}",
                agent_id=f"a{suffix}",
            )
        )
        await s.commit()

    async with factory() as s:
        await replace_extra_roots(s, f"pr{suffix}", ["/tmp/a", "/tmp/b"])
        await s.commit()
        assert await load_extra_roots(s, f"pr{suffix}") == ["/tmp/a", "/tmp/b"]
        agent = await s.get(Agent, f"a{suffix}")
        assert agent.description == long_text
        assert agent.instructions == long_text
        project = await s.get(Project, f"pr{suffix}")
        assert project.path == "/tmp/" + long_text

        s.add(
            TurnRow(
                id=f"t{suffix}",
                session_id=f"s{suffix}",
                role="user",
                content=long_text,
            )
        )
        await s.commit()

    with pytest.raises(IntegrityError):
        async with factory() as s:
            s.add(
                SessionRow(
                    id=f"bad{suffix}",
                    project_id="missing",
                    agent_id="missing",
                )
            )
            await s.commit()

    async with factory() as s:
        session = await s.get(SessionRow, f"s{suffix}")
        await s.delete(session)
        await s.commit()
        assert await s.get(TurnRow, f"t{suffix}") is None

    await engine.dispose()
