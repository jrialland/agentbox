import pathlib

import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_harness.session import Turn
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.repos.message_log import SQLiteMessageLogStore
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
        "agentbox_api.runtime.resolve_model",
        lambda provider, name, context_window=None: TestModel(call_tools=[]),
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


async def test_cancel_endpoint_is_idempotent_and_409_when_idle(tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    await _seed(factory, tmp_path)
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)

    class FakeRun:
        cancelled = False

        def cancel(self):
            self.cancelled = True

    run = FakeRun()
    app.state.run_registry.register("s1", run)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        token = (
            await client.post(
                "/auth/login", json={"username": "alice", "password": "pw"}
            )
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.post("/sessions/s1/messages/cancel", headers=headers)
        assert r.status_code == 202
        assert run.cancelled is True

        app.state.run_registry.finish("s1")
        r = await client.post("/sessions/s1/messages/cancel", headers=headers)
        assert r.status_code == 409

    await engine.dispose()


async def test_retry_turn_id_does_not_duplicate_user_turn(tmp_path, monkeypatch):
    from pydantic_ai.models.test import TestModel

    monkeypatch.setattr(
        "agentbox_api.runtime.resolve_model",
        lambda provider, name, context_window=None: TestModel(call_tools=[]),
    )
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    await _seed(factory, tmp_path)
    store = SQLiteMessageLogStore(factory, "s1")
    await store.append(Turn(id="u1", role="user", content="original", parent_id=None))

    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        token = (
            await client.post(
                "/auth/login", json={"username": "alice", "password": "pw"}
            )
        ).json()["access_token"]
        async with client.stream(
            "POST",
            "/sessions/s1/messages",
            json={"content": "ignored", "retry_turn_id": "u1"},
            headers={"Authorization": f"Bearer {token}"},
        ) as r:
            body = "".join([chunk async for chunk in r.aiter_text()])
        assert "RUN_FINISHED" in body

    turns = await store.list_turns()
    assert [t.role for t in turns].count("user") == 1
    assert any(t.role == "assistant" and t.parent_id == "u1" for t in turns)
    await engine.dispose()


async def test_run_error_is_streamed_and_persisted(tmp_path, monkeypatch):
    from pydantic_ai.models.function import FunctionModel

    async def fail_stream(messages, info):
        raise RuntimeError("boom")
        yield ""

    monkeypatch.setattr(
        "agentbox_api.runtime.resolve_model",
        lambda provider, name, context_window=None: FunctionModel(
            stream_function=fail_stream
        ),
    )
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    await _seed(factory, tmp_path)
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        token = (
            await client.post(
                "/auth/login", json={"username": "alice", "password": "pw"}
            )
        ).json()["access_token"]
        async with client.stream(
            "POST",
            "/sessions/s1/messages",
            json={"content": "fail please"},
            headers={"Authorization": f"Bearer {token}"},
        ) as r:
            body = "".join([chunk async for chunk in r.aiter_text()])
        assert "RUN_ERROR" in body

    turns = await SQLiteMessageLogStore(factory, "s1").list_turns()
    assistant = next(t for t in turns if t.role == "assistant")
    assert assistant.activity is not None
    assert assistant.activity["status"] == "error"
    await engine.dispose()
