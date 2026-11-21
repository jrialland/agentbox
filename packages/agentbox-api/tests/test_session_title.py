import pathlib

import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.routers.sessions import derive_session_title
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import Permission, Role, RolePermissionLink, User, UserRoleLink
from agentbox_models.tables.core import Agent, Model, Project, Provider, SessionRow


def test_derive_session_title_normalizes_and_truncates():
    assert derive_session_title("  hello \n world  ") == "hello world"
    title = derive_session_title("x" * 80)
    assert len(title) == 60
    assert title.endswith("...")


async def _seed(factory, tmp_path: pathlib.Path):
    async with factory() as s:
        s.add(Provider(id="p", name="test", kind="generic", base_url="http://localhost:1"))
        s.add(Model(id="m", provider_id="p", name="test-model"))
        s.add(Agent(id="a", name="bot", description="", instructions="", model_id="m"))
        s.add(Project(id="prj", name="proj", path=str(tmp_path), owner_id="u1"))
        s.add(SessionRow(id="s1", project_id="prj", agent_id="a"))
        s.add(User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw")))
        s.add(Role(id="r1", name="role"))
        s.add(Permission(id="perm1", name="sessions:create"))
        s.add(Permission(id="perm2", name="sessions:read"))
        s.add(RolePermissionLink(role_id="r1", permission_id="perm1"))
        s.add(RolePermissionLink(role_id="r1", permission_id="perm2"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        await s.commit()


async def _login(client):
    token = (
        await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_rename_session_and_reject_blank(tmp_path: pathlib.Path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    await _seed(factory, tmp_path)
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        headers = await _login(client)
        response = await client.patch(
            "/sessions/s1", json={"title": " Release plan "}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Release plan"

        response = await client.patch("/sessions/s1", json={"title": "   "}, headers=headers)
        assert response.status_code == 422
    finally:
        await client.aclose()
        await engine.dispose()


async def test_first_message_sets_title_once(tmp_path: pathlib.Path, monkeypatch):
    from pydantic_ai.models.test import TestModel

    monkeypatch.setattr(
        "agentbox_api.runtime.resolve_model",
        lambda provider, name, context_window=None: TestModel(call_tools=[]),
    )
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    await _seed(factory, tmp_path)
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        headers = await _login(client)
        async with client.stream(
            "POST", "/sessions/s1/messages", json={"content": "Plan the release"}, headers=headers
        ) as response:
            _ = [chunk async for chunk in response.aiter_text()]
        async with factory() as session:
            row = await session.get(SessionRow, "s1")
            assert row is not None
            assert row.title == "Plan the release"
    finally:
        await client.aclose()
        await engine.dispose()
