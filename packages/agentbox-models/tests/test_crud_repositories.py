from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.repos.crud import UserRepository
from agentbox_models.tables.auth import User


async def test_user_repository_crud():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    repo = UserRepository(factory)
    await repo.create(
        User(id="u1", username="alice", email="a@x.com", password_hash="h")
    )
    user = await repo.get("u1")
    assert user is not None and user.username == "alice"
    await repo.delete("u1")
    assert await repo.get("u1") is None
    await engine.dispose()
