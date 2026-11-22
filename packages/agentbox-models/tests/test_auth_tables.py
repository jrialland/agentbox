from sqlmodel import select

from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import (
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)


async def test_rbac_relations():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        u = User(id="u1", username="alice", email="a@x.com", password_hash="h")
        r = Role(id="r1", name="admin")
        p = Permission(id="p1", name="manage_users")
        s.add_all([u, r, p])
        await s.commit()
        s.add(RolePermissionLink(role_id="r1", permission_id="p1"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        await s.commit()
        roles = (
            await s.execute(select(UserRoleLink).where(UserRoleLink.user_id == "u1"))
        ).scalars().all()
        assert len(roles) == 1
        assert roles[0].role_id == "r1"
    await engine.dispose()


async def test_api_key_scopes_roundtrip():
    from agentbox_models.repos.api_key_scopes import load_scopes, replace_scopes
    from agentbox_models.tables.auth import ApiKey

    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="a", email="a@x", password_hash="h"))
        await s.flush()
        s.add(ApiKey(id="k1", user_id="u1", key_hash="h"))
        await s.commit()
        await replace_scopes(s, "k1", ["agents:read", "sessions:create"])
        await s.commit()
        assert await load_scopes(s, "k1") == ["agents:read", "sessions:create"]
    await engine.dispose()
