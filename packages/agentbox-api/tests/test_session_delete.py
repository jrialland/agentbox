import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import (
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)
from agentbox_models.tables.core import (
    Agent,
    Model,
    Project,
    Provider,
    SessionAttachment,
    SessionRow,
    TurnRow,
)


async def test_session_delete_removes_everything():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r1", name="role"))
        s.add(Permission(id="p0", name="sessions:create"))
        s.add(RolePermissionLink(role_id="r1", permission_id="p0"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(Provider(id="prov", name="test", kind="test"))
        s.add(Model(id="m", provider_id="prov", name="mm"))
        s.add(Agent(id="ag", name="a", description="", instructions="", model_id="m"))
        s.add(Project(id="prj", name="p", path=".", owner_id="u1"))
        s.add(SessionRow(id="s1", project_id="prj", agent_id="ag"))
        s.add(TurnRow(id="t1", session_id="s1", role="user", content="hi"))
        s.add(
            SessionAttachment(
                id="a1", session_id="s1", media_type="text/plain", filename="f", data=b"x"
            )
        )
        await s.commit()
    app = create_app(
        Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    try:
        token = (
            await client.post(
                "/auth/login", json={"username": "alice", "password": "pw"}
            )
        ).json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        assert (await client.delete("/sessions/s1", headers=h)).status_code == 200
        async with factory() as s:
            assert await s.get(SessionRow, "s1") is None
            assert await s.get(TurnRow, "t1") is None
            assert await s.get(SessionAttachment, "a1") is None
    finally:
        await client.aclose()
        await engine.dispose()
