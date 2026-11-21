import pathlib
import sys

import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_harness.tools.mcp_session import get_mcp_session_manager
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import (
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)
from agentbox_models.tables.core import Agent, Model, Project, Provider, SessionRow

SERVER = pathlib.Path(__file__).with_name("stdio_app_server.py")


async def _setup(tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            User(
                id="u1",
                username="alice",
                email="a@x",
                password_hash=hash_password("pw"),
            )
        )
        s.add(Role(id="r_u1", name="role"))
        for i, p in enumerate(
            ["sessions:create", "sessions:read", "agents:create", "agents:read"]
        ):
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
                tool_bindings="[]",
                mode_definitions='[{"name":"agent","flags":{"write":true}}]',
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


async def _login(client) -> dict[str, str]:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_stdio_server_is_reused_across_turns(tmp_path):
    engine, client = await _setup(tmp_path)
    try:
        h = await _login(client)
        r = await client.put(
            "/agents/agent",
            json={
                "name": "agent",
                "model": "test-model",
                "tool_bindings": [
                    {
                        "id": "echo",
                        "command": sys.executable,
                        "args": [str(SERVER)],
                    }
                ],
            },
            headers=h,
        )
        assert r.status_code == 200

        await client.post("/sessions/s1/messages", json={"content": "hi"}, headers=h)
        first = get_mcp_session_manager()._entries["s1"].toolsets[0]
        await client.post(
            "/sessions/s1/messages", json={"content": "again"}, headers=h
        )
        second = get_mcp_session_manager()._entries["s1"].toolsets[0]
        assert first is second
    finally:
        await get_mcp_session_manager().close_all()
        await client.aclose()
        await engine.dispose()


async def test_broken_server_emits_warning_and_run_succeeds(tmp_path):
    engine, client = await _setup(tmp_path)
    try:
        h = await _login(client)
        r = await client.put(
            "/agents/agent",
            json={
                "name": "agent",
                "model": "test-model",
                "tool_bindings": [
                    {"id": "broken", "command": "definitely-not-a-real-command-xyz"}
                ],
            },
            headers=h,
        )
        assert r.status_code == 200

        r = await client.post(
            "/sessions/s1/messages", json={"content": "hi"}, headers=h
        )
        assert r.status_code == 200
        assert "mcp.warning" in r.text
        assert "broken" in r.text
    finally:
        await get_mcp_session_manager().close_all()
        await client.aclose()
        await engine.dispose()


async def test_delete_session_closes_mcp_process(tmp_path):
    engine, client = await _setup(tmp_path)
    try:
        h = await _login(client)
        await client.put(
            "/agents/agent",
            json={
                "name": "agent",
                "model": "test-model",
                "tool_bindings": [
                    {"id": "echo", "command": sys.executable, "args": [str(SERVER)]}
                ],
            },
            headers=h,
        )
        await client.post("/sessions/s1/messages", json={"content": "hi"}, headers=h)
        assert "s1" in get_mcp_session_manager()._entries
        r = await client.delete("/sessions/s1", headers=h)
        assert r.status_code == 200
        assert "s1" not in get_mcp_session_manager()._entries
    finally:
        await get_mcp_session_manager().close_all()
        await client.aclose()
        await engine.dispose()
