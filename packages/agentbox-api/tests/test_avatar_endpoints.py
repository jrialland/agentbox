import io

import httpx
from PIL import Image

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


async def _setup():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r_u1", name="role"))
        for i, p in enumerate(["agents:create", "agents:read", "sessions:read"]):
            s.add(Permission(id=f"p{i}_u1", name=p))
            s.add(RolePermissionLink(role_id="r_u1", permission_id=f"p{i}_u1"))
        s.add(UserRoleLink(user_id="u1", role_id="r_u1"))
        s.add(Provider(id="prov", name="test", kind="test"))
        s.add(Model(id="m", provider_id="prov", name="test-model"))
        s.add(Agent(id="ag", name="bot", description="", instructions="", model_id="m"))
        s.add(Project(id="prj", name="p", path=".", owner_id="u1"))
        s.add(SessionRow(id="s1", project_id="prj", agent_id="ag"))
        await s.commit()
    app = create_app(
        Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    return engine, client


def _png(size=(400, 200)) -> bytes:
    img = Image.new("RGB", size, "red")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


async def _auth(client) -> dict:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_default_avatar_public_and_deterministic():
    engine, client = await _setup()
    try:
        r1 = await client.get("/agents/bot/avatar")
        r2 = await client.get("/agents/bot/avatar")
        assert r1.status_code == 200
        assert r1.headers["content-type"] == "image/png"
        assert r1.content == r2.content
    finally:
        await client.aclose()
        await engine.dispose()


async def test_unknown_agent_404():
    engine, client = await _setup()
    try:
        assert (await client.get("/agents/nope/avatar")).status_code == 404
    finally:
        await client.aclose()
        await engine.dispose()


async def test_upload_then_reset():
    engine, client = await _setup()
    try:
        h = await _auth(client)
        before = (await client.get("/agents/bot/avatar")).content
        up = await client.put(
            "/agents/bot/avatar",
            files={"file": ("a.png", _png(), "image/png")},
            headers=h,
        )
        assert up.status_code == 204
        after = await client.get("/agents/bot/avatar")
        assert after.content != before
        with Image.open(io.BytesIO(after.content)) as im:
            assert im.size == (300, 300)
        rm = await client.delete("/agents/bot/avatar", headers=h)
        assert rm.status_code == 204
        assert (await client.get("/agents/bot/avatar")).content == before
    finally:
        await client.aclose()
        await engine.dispose()


async def test_upload_rejects_bad_type_and_size():
    engine, client = await _setup()
    try:
        h = await _auth(client)
        bad = await client.put(
            "/agents/bot/avatar",
            files={"file": ("a.txt", b"x", "text/plain")},
            headers=h,
        )
        assert bad.status_code == 415
        big = await client.put(
            "/agents/bot/avatar",
            files={"file": ("a.png", b"x" * (2 * 1024 * 1024 + 1), "image/png")},
            headers=h,
        )
        assert big.status_code == 413
    finally:
        await client.aclose()
        await engine.dispose()


async def test_session_detail_has_agent_name():
    engine, client = await _setup()
    try:
        h = await _auth(client)
        r = await client.get("/sessions/s1", headers=h)
        assert r.status_code == 200
        assert r.json()["agent_name"] == "bot"
    finally:
        await client.aclose()
        await engine.dispose()
