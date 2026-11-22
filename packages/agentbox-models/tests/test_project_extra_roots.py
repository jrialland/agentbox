from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.repos.project_roots import load_extra_roots, replace_extra_roots
from agentbox_models.tables.auth import User
from agentbox_models.tables.core import Project


async def test_project_extra_roots_roundtrip():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="a", email="a@x", password_hash="h"))
        s.add(Project(id="p1", name="p", path="/tmp/p", owner_id="u1"))
        await s.commit()
        await replace_extra_roots(s, "p1", ["/tmp/a", "/tmp/b"])
        await s.commit()
        assert await load_extra_roots(s, "p1") == ["/tmp/a", "/tmp/b"]
        await replace_extra_roots(s, "p1", ["/tmp/c"])
        await s.commit()
        assert await load_extra_roots(s, "p1") == ["/tmp/c"]
    await engine.dispose()
