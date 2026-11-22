import asyncio
import json
import socket
import uuid

import httpx
import uvicorn
from a2a import helpers as a2a_helpers
from a2a import types as a2a_types
from a2a.client import ClientConfig, create_client

from agentbox_api.a2a_server import build_card
from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.media import MediaStore
from agentbox_api.security import hash_api_key, hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import (
    ApiKey,
    ApiKeyScope,
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)
from agentbox_models.tables.core import Agent, AgentCard, MediaFile, Model, Provider


async def _setup(tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r1", name="role"))
        for i, p in enumerate(["agents:create", "agents:read"]):
            s.add(Permission(id=f"p{i}", name=p))
            s.add(RolePermissionLink(role_id="r1", permission_id=f"p{i}"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        await s.flush()
        s.add(
            ApiKey(
                id="k1",
                user_id="u1",
                key_hash=hash_api_key("testkey"),
            )
        )
        await s.flush()
        s.add(ApiKeyScope(api_key_id="k1", scope="sessions:create"))
        s.add(Provider(id="prov", name="test", kind="test"))
        await s.flush()
        s.add(Model(id="m", provider_id="prov", name="test-model"))
        await s.flush()
        s.add(Agent(id="ag", name="bot", description="d", instructions="i", model_id="m"))
        await s.commit()
    app = create_app(
        Settings(jwt_secret="s" * 32, media_dir=str(tmp_path / "media")),
        engine=engine,
        session_factory=factory,
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    return engine, client


async def _auth(client) -> dict:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_agent_card_crud(tmp_path):
    engine, client = await _setup(tmp_path)
    try:
        h = await _auth(client)
        assert (await client.get("/agents/bot/card", headers=h)).status_code == 404
        r = await client.put(
            "/agents/bot/card",
            json={"name": "Bot", "description": "d", "version": "1.0.0", "skills": []},
            headers=h,
        )
        assert r.status_code == 200
        assert (await client.get("/agents/bot/card", headers=h)).json()["name"] == "Bot"
        assert (await client.delete("/agents/bot/card", headers=h)).status_code == 200
        assert (await client.get("/agents/bot/card", headers=h)).status_code == 404
    finally:
        await client.aclose()
        await engine.dispose()


async def test_a2a_requires_api_key_and_discovers_card(tmp_path):
    engine, client = await _setup(tmp_path)
    try:
        assert (
            await client.get("/a2a/bot/.well-known/agent-card.json")
        ).status_code == 401
        h = await _auth(client)
        await client.put(
            "/agents/bot/card",
            json={"name": "Bot", "description": "d", "version": "1.0.0", "skills": []},
            headers=h,
        )
        assert (
            await client.get("/a2a/bot/.well-known/agent-card.json", headers=h)
        ).status_code == 403
        key_h = {"Authorization": "Bearer testkey"}
        r = await client.get("/a2a/bot/.well-known/agent-card.json", headers=key_h)
        assert r.status_code == 200
        assert r.json()["name"] == "Bot"
    finally:
        await client.aclose()
        await engine.dispose()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_a2a_message_send_protocol(tmp_path):
    port = _free_port()
    db = tmp_path / "a2a.db"
    url = f"sqlite+aiosqlite:///{db.as_posix()}"
    engine, factory = create_engine_and_sessionmaker(url)
    await init_db(engine)
    media_dir = tmp_path / "media"
    stored = MediaStore(media_dir).save(
        json.dumps(
            {"name": "Bot", "description": "d", "version": "1.0.0", "skills": []}
        ).encode(),
        category="agent-cards",
        media_type="application/json",
        suffix=".json",
    )
    media_id = uuid.uuid4().hex
    async with factory() as s:
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        await s.flush()
        s.add(
            ApiKey(
                id="k1",
                user_id="u1",
                key_hash=hash_api_key("testkey"),
            )
        )
        await s.flush()
        s.add(ApiKeyScope(api_key_id="k1", scope="sessions:create"))
        s.add(Provider(id="prov", name="test", kind="test"))
        await s.flush()
        s.add(Model(id="m", provider_id="prov", name="test-model"))
        await s.flush()
        s.add(
            Agent(
                id="ag",
                name="bot",
                description="d",
                instructions="i",
                model_id="m",
            )
        )
        s.add(
            MediaFile(
                id=media_id,
                storage_path=stored.storage_path,
                media_type=stored.media_type,
                size_bytes=stored.size_bytes,
                sha256=stored.sha256,
            )
        )
        await s.flush()
        s.add(
            AgentCard(
                id="card1",
                agent_id="ag",
                file_id=media_id,
            )
        )
        await s.commit()

    settings = Settings(
        jwt_secret="s" * 32,
        a2a_public_url=f"http://127.0.0.1:{port}",
        media_dir=str(media_dir),
    )
    app = create_app(settings, engine=engine, session_factory=factory)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    serve_task = asyncio.create_task(server.serve())
    try:
        for _ in range(200):
            if server.started:
                break
            await asyncio.sleep(0.05)
        card = build_card(
            {"name": "Bot", "description": "d", "version": "1.0.0", "skills": []},
            "bot",
            f"http://127.0.0.1:{port}",
        )
        http = httpx.AsyncClient(headers={"Authorization": "Bearer testkey"})
        try:
            client = await create_client(
                agent=card, client_config=ClientConfig(httpx_client=http)
            )
            request = a2a_types.SendMessageRequest(
                message=a2a_helpers.new_text_message("hi", role=a2a_types.Role.ROLE_USER)
            )
            texts = []
            async for resp in client.send_message(request):
                text = a2a_helpers.get_stream_response_text(resp)
                if text:
                    texts.append(text)
            assert "Hello from the test provider" in "".join(texts)
        finally:
            await http.aclose()
    finally:
        server.should_exit = True
        await serve_task
        await engine.dispose()




