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


async def _make_app(perms: list[str], tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        await s.flush()
        s.add(
            User(
                id="u1",
                username="alice",
                email="a@x",
                password_hash=hash_password("pw"),
            )
        )
        s.add(Role(id="r_u1", name="role"))
        for i, p in enumerate(perms):
            s.add(Permission(id=f"p{i}_u1", name=p))
            await s.flush()
            s.add(RolePermissionLink(role_id="r_u1", permission_id=f"p{i}_u1"))
        await s.flush()
        s.add(UserRoleLink(user_id="u1", role_id="r_u1"))
        s.add(Provider(id="prov", name="test", kind="test"))
        await s.flush()
        await s.flush()
        s.add(Model(id="m", provider_id="prov", name="test-model"))
        await s.flush()
        await s.flush()
        s.add(Agent(id="ag", name="bot", description="", instructions="", model_id="m"))
        await s.flush()
        s.add(Project(id="prj", name="p", path=".", owner_id="u1"))
        await s.flush()
        await s.flush()
        s.add(SessionRow(id="s1", project_id="prj", agent_id="ag"))
        await s.commit()
    media_dir = tmp_path / "media"
    app = create_app(
        Settings(jwt_secret="s" * 32, media_dir=str(media_dir)),
        engine=engine,
        session_factory=factory,
    )
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return engine, client, media_dir


async def _login(client) -> str:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return r.json()["access_token"]


async def test_upload_attachment(tmp_path):
    engine, client, media_dir = await _make_app(["sessions:create"], tmp_path)
    try:
        token = await _login(client)
        r = await client.post(
            "/sessions/s1/attachments",
            files={"file": ("note.txt", b"hello", "text/plain")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["id"]
        assert body["filename"] == "note.txt"
        assert body["media_type"] == "text/plain"
        assert any((media_dir / "attachments").iterdir())
    finally:
        await client.aclose()
        await engine.dispose()


async def test_download_attachment_returns_bytes_and_headers(tmp_path):
    engine, client, _media_dir = await _make_app(
        ["sessions:create", "sessions:read"], tmp_path
    )
    try:
        token = await _login(client)
        upload = await client.post(
            "/sessions/s1/attachments",
            files={"file": ("note.txt", b"hello", "text/plain")},
            headers={"Authorization": f"Bearer {token}"},
        )
        attachment_id = upload.json()["id"]

        r = await client.get(
            f"/sessions/s1/attachments/{attachment_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.content == b"hello"
        assert r.headers["content-type"].startswith("text/plain")
        assert 'filename="note.txt"' in r.headers["content-disposition"]

        missing = await client.get(
            f"/sessions/other/attachments/{attachment_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert missing.status_code == 404
    finally:
        await client.aclose()
        await engine.dispose()
