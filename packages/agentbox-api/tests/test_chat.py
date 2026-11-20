import pathlib

import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import Permission, Role, RolePermissionLink, User, UserRoleLink
from agentbox_models.tables.core import Agent, Model, Project, Provider, SessionRow


async def _seed(factory, tmp_path: pathlib.Path):
    async with factory() as s:
        s.add(Provider(id="p", name="test", kind="generic", base_url="http://localhost:1"))
        s.add(Model(id="m", provider_id="p", name="test-model"))
        s.add(
            Agent(
                id="ag",
                name="coder",
                description="d",
                instructions="i",
                model_id="m",
                tool_bindings="[]",
                mode_definitions='[{"name": "agent", "flags": {}}]',
                sub_agent_ids="[]",
            )
        )
        s.add(Project(id="prj", name="proj", path=str(tmp_path), owner_id="u1"))
        s.add(SessionRow(id="s1", project_id="prj", agent_id="ag"))
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r1", name="role"))
        s.add(Permission(id="perm1", name="sessions:create"))
        s.add(RolePermissionLink(role_id="r1", permission_id="perm1"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        await s.commit()


async def test_chat_streams_run_events(tmp_path, monkeypatch):
    from pydantic_ai.models.test import TestModel

    monkeypatch.setattr(
        "agentbox_api.runtime.resolve_model", lambda provider, name: TestModel(call_tools=[])
    )

    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    await _seed(factory, tmp_path)

    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
        token = login.json()["access_token"]
        async with client.stream(
            "POST",
            "/sessions/s1/messages",
            json={"content": "hi"},
            headers={"Authorization": f"Bearer {token}"},
        ) as r:
            body = "".join([chunk async for chunk in r.aiter_text()])

    assert "RUN_STARTED" in body
    assert "RUN_FINISHED" in body
    await engine.dispose()
