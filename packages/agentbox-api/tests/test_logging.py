import contextlib

import httpx
from loguru import logger

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
from agentbox_models.tables.core import Model, Provider


class Capture:
    def __init__(self):
        self.messages: list[str] = []
        self._id = None

    def __enter__(self):
        self._id = logger.add(self.messages.append, level="DEBUG", format="{message}")
        return self

    def __exit__(self, *exc):
        if self._id is not None:
            logger.remove(self._id)

    def text(self) -> str:
        return "\n".join(self.messages)


async def _app_with_user(username="alice", password="secret"):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            User(
                id="u1",
                username=username,
                email=f"{username}@x",
                password_hash=hash_password(password),
            )
        )
        await s.commit()
    app = create_app(
        Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    return engine, client


async def test_login_logs_success_without_password():
    engine, client = await _app_with_user()
    try:
        with Capture() as cap:
            r = await client.post(
                "/auth/login", json={"username": "alice", "password": "secret"}
            )
        assert r.status_code == 200
        text = cap.text()
        assert "login ok" in text
        assert "user=alice" in text
        assert "secret" not in text
    finally:
        await client.aclose()
        await engine.dispose()


async def test_login_failure_logs_warning():
    engine, client = await _app_with_user()
    try:
        with Capture() as cap:
            r = await client.post(
                "/auth/login", json={"username": "alice", "password": "wrong"}
            )
        assert r.status_code == 401
        assert "login failed" in cap.text()
        assert "user=alice" in cap.text()
        assert "wrong" not in cap.text()
    finally:
        await client.aclose()
        await engine.dispose()


async def _app_with_perms(perms: list[str]):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r_u1", name="role"))
        for i, p in enumerate(perms):
            s.add(Permission(id=f"p{i}_u1", name=p))
            s.add(RolePermissionLink(role_id="r_u1", permission_id=f"p{i}_u1"))
        s.add(UserRoleLink(user_id="u1", role_id="r_u1"))
        s.add(Provider(id="prov", name="test", kind="test"))
        s.add(Model(id="m", provider_id="prov", name="test-model"))
        await s.commit()
    app = create_app(
        Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    return engine, client


async def _token(client) -> str:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return r.json()["access_token"]


async def test_project_create_logs():
    engine, client = await _app_with_perms(["projects:create"])
    try:
        h = {"Authorization": f"Bearer {await _token(client)}"}
        with Capture() as cap:
            r = await client.post(
                "/projects", json={"name": "p", "path": "."}, headers=h
            )
        assert r.status_code == 200
        assert "project created" in cap.text()
    finally:
        await client.aclose()
        await engine.dispose()


async def test_api_key_create_does_not_log_raw_key():
    engine, client = await _app_with_perms(["api_keys:manage"])
    try:
        h = {"Authorization": f"Bearer {await _token(client)}"}
        with Capture() as cap:
            r = await client.post("/api-keys", json={"scopes": []}, headers=h)
        raw = r.json()["key"]
        text = cap.text()
        assert "api key created" in text
        assert raw not in text
    finally:
        await client.aclose()
        await engine.dispose()


async def _app_with_chat():
    engine, client = await _app_with_perms(
        ["sessions:create", "sessions:read", "projects:create", "agents:create"]
    )
    h = {"Authorization": f"Bearer {await _token(client)}"}
    await client.post(
        "/agents",
        json={
            "name": "bot",
            "model": "test-model",
            "tool_bindings": [],
            "mode_definitions": [
                {"name": "ask", "flags": {"write": False}},
                {"name": "agent", "flags": {"write": True}},
            ],
        },
        headers=h,
    )
    proj = await client.post("/projects", json={"name": "p", "path": "."}, headers=h)
    return engine, client, h, proj.json()["id"]


async def test_session_create_logs():
    engine, client, h, project_id = await _app_with_chat()
    try:
        with Capture() as cap:
            r = await client.post(
                "/sessions",
                json={"project_id": project_id, "agent_id": "bot"},
                headers=h,
            )
        assert r.status_code == 200
        assert "session created" in cap.text()
    finally:
        await client.aclose()
        await engine.dispose()


async def test_session_run_lifecycle_logs():
    engine, client, h, project_id = await _app_with_chat()
    try:
        sid = (
            await client.post(
                "/sessions",
                json={"project_id": project_id, "agent_id": "bot"},
                headers=h,
            )
        ).json()["id"]
        with Capture() as cap:
            r = await client.post(
                f"/sessions/{sid}/messages", json={"content": "hi"}, headers=h
            )
        assert r.status_code == 200
        text = cap.text()
        assert "run start" in text
        assert "run finished" in text
    finally:
        await client.aclose()
        await engine.dispose()


async def test_relay_unknown_server_logs_error():
    from agentbox_api import mcp_relay
    from agentbox_harness.spec import AgentSpec, ModelBinding

    spec = AgentSpec(
        name="a",
        description="",
        instructions="",
        tool_bindings=[],
        model_binding=ModelBinding(model="test", provider="test"),
    )
    with Capture() as cap, contextlib.suppress(KeyError):
        await mcp_relay.read_resource_for_app(spec, "missing", "ui://x/a.html")
    assert "mcp server not found" in cap.text()


async def test_configure_logging_writes_file_and_intercepts(tmp_path):
    import logging as stdlib_logging

    from agentbox_api.logging import InterceptHandler, configure_logging

    settings = Settings(jwt_secret="s" * 32, log_dir=str(tmp_path), log_level="DEBUG")
    configure_logging(settings)
    logger.info("hello sink")
    target = stdlib_logging.getLogger("agentbox.test.intercept")
    target.handlers = [InterceptHandler()]
    target.propagate = False
    target.disabled = False
    target.setLevel(stdlib_logging.DEBUG)
    target.info("intercepted stdlib")
    await logger.complete()
    import asyncio

    await asyncio.sleep(0.2)
    path = tmp_path / "agentbox.log"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "hello sink" in text
    assert "intercepted stdlib" in text
