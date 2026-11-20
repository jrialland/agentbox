"""MCP Apps: the chat stream emits an ACTIVITY_SNAPSHOT for app tool results."""

from __future__ import annotations

import json

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


async def _setup(tmp_path, mcp_url):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r_u1", name="role"))
        for i, p in enumerate(["sessions:create", "sessions:read"]):
            s.add(Permission(id=f"p{i}_u1", name=p))
            s.add(RolePermissionLink(role_id="r_u1", permission_id=f"p{i}_u1"))
        s.add(UserRoleLink(user_id="u1", role_id="r_u1"))
        s.add(Provider(id="prov", name="test", kind="test"))
        s.add(Model(id="m", provider_id="prov", name="test-model"))
        s.add(
            Agent(
                id="ag",
                name="agent",
                description="d",
                instructions="i",
                model_id="m",
                tool_bindings=json.dumps([{"server_url": mcp_url, "id": "test-app"}]),
                mode_definitions='[{"name":"ask","flags":{"write":false}},{"name":"agent","flags":{"write":true}}]',
                sub_agent_ids="[]",
            )
        )
        s.add(Project(id="prj", name="p", path=str(tmp_path), owner_id="u1"))
        s.add(SessionRow(id="s1", project_id="prj", agent_id="ag"))
        await s.commit()
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    return engine, client


async def _login(client) -> str:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return r.json()["access_token"]


async def test_app_tool_emits_activity_snapshot(tmp_path, mcp_server_url, monkeypatch):
    from pydantic_ai.models.test import TestModel

    monkeypatch.setattr(
        "agentbox_api.runtime.resolve_model",
        lambda provider, name, context_window=None: TestModel(call_tools=["show_app"]),
    )

    engine, client = await _setup(tmp_path, mcp_server_url)
    try:
        token = await _login(client)
        h = {"Authorization": f"Bearer {token}"}
        r = await client.post(
            "/sessions/s1/messages", json={"content": "show the app"}, headers=h
        )
        assert r.status_code == 200
        body = r.text
        assert "ACTIVITY_SNAPSHOT" in body
        assert "mcp-apps" in body
        assert "ui://test/app.html" in body
    finally:
        await client.aclose()
        await engine.dispose()
