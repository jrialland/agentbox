from starlette.authentication import AuthCredentials

from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import (
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)

from agentbox_api.auth_backend import JWTAuthenticationBackend, load_user_permissions
from agentbox_api.config import Settings
from agentbox_api.security import create_jwt


async def test_load_user_permissions():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="a", email="a@x", password_hash="h"))
        s.add(Role(id="r1", name="admin"))
        s.add(Permission(id="p1", name="agents:read"))
        s.add(RolePermissionLink(role_id="r1", permission_id="p1"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        await s.commit()
        perms = await load_user_permissions(s, "u1")
        assert perms == {"agents:read"}
    await engine.dispose()


async def test_authenticate_jwt():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="a", email="a@x", password_hash="h"))
        s.add(Role(id="r1", name="admin"))
        s.add(Permission(id="p1", name="agents:read"))
        s.add(RolePermissionLink(role_id="r1", permission_id="p1"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        await s.commit()

    settings = Settings(jwt_secret="s" * 32)
    backend = JWTAuthenticationBackend(factory, settings)
    token = create_jwt("u1", "s" * 32, "HS256", 3600)

    class Req:
        def __init__(self, h):
            self.headers = h

    creds, user = await backend.authenticate(Req({"Authorization": f"Bearer {token}"}))
    assert isinstance(creds, AuthCredentials)
    assert "agents:read" in creds.scopes
    assert user.display_name == "a"
    await engine.dispose()
