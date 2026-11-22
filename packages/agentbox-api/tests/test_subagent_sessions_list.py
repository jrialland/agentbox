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
from agentbox_models.tables.core import Agent, Model, Project, Provider, SessionRow


async def test_session_list_hides_children():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        await s.flush()
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r1", name="role"))
        s.add(Permission(id="perm", name="sessions:read"))
        await s.flush()
        s.add(RolePermissionLink(role_id="r1", permission_id="perm"))
        await s.flush()
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        await s.flush()
        s.add(Provider(id="prov", name="test", kind="test"))
        await s.flush()
        s.add(Model(id="m", provider_id="prov", name="test-model"))
        await s.flush()
        s.add(Agent(id="a", name="a", description="", instructions="", model_id="m"))
        s.add(Agent(id="b", name="b", description="", instructions="", model_id="m"))
        s.add(Project(id="p", name="p", path=".", owner_id="u1"))
        await s.flush()
        s.add(SessionRow(id="parent", project_id="p", agent_id="a"))
        await s.flush()
        s.add(
            SessionRow(
                id="child",
                project_id="p",
                agent_id="b",
                parent_session_id="parent",
                subagent_session_status="completed",
                subagent_session_depth=1,
            )
        )
        await s.commit()

    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    try:
        login = await client.post(
            "/auth/login", json={"username": "alice", "password": "pw"}
        )
        response = await client.get(
            "/sessions",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert response.status_code == 200
        assert [row["id"] for row in response.json()] == ["parent"]
    finally:
        await client.aclose()
        await engine.dispose()
