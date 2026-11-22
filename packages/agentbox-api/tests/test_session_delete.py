import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.media import MediaStore
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import (
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)
from agentbox_models.tables.core import (
    Agent,
    MediaFile,
    Model,
    Project,
    Provider,
    SessionAttachment,
    SessionRow,
    TurnRow,
)


async def test_session_delete_removes_everything(tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    media_dir = tmp_path / "media"
    stored = MediaStore(media_dir).save(
        b"x", category="attachments", media_type="text/plain", suffix=".txt"
    )
    async with factory() as s:
        await s.flush()
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r1", name="role"))
        s.add(Permission(id="p0", name="sessions:create"))
        await s.flush()
        s.add(RolePermissionLink(role_id="r1", permission_id="p0"))
        await s.flush()
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(Provider(id="prov", name="test", kind="test"))
        await s.flush()
        await s.flush()
        s.add(Model(id="m", provider_id="prov", name="mm"))
        await s.flush()
        await s.flush()
        s.add(Agent(id="ag", name="a", description="", instructions="", model_id="m"))
        await s.flush()
        s.add(Project(id="prj", name="p", path=".", owner_id="u1"))
        await s.flush()
        await s.flush()
        s.add(SessionRow(id="s1", project_id="prj", agent_id="ag"))
        await s.flush()
        s.add(TurnRow(id="t1", session_id="s1", role="user", content="hi"))
        await s.flush()
        s.add(
            MediaFile(
                id="f1",
                storage_path=stored.storage_path,
                media_type=stored.media_type,
                size_bytes=stored.size_bytes,
                sha256=stored.sha256,
            )
        )
        await s.flush()
        await s.flush()
        s.add(
            SessionAttachment(
                id="a1", session_id="s1", file_id="f1", filename="f"
            )
        )
        await s.commit()
    app = create_app(
        Settings(jwt_secret="s" * 32, media_dir=str(media_dir)),
        engine=engine,
        session_factory=factory,
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    try:
        token = (
            await client.post(
                "/auth/login", json={"username": "alice", "password": "pw"}
            )
        ).json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        assert (await client.delete("/sessions/s1", headers=h)).status_code == 200
        async with factory() as s:
            assert await s.get(SessionRow, "s1") is None
            assert await s.get(TurnRow, "t1") is None
            assert await s.get(SessionAttachment, "a1") is None
            assert await s.get(MediaFile, "f1") is None
        assert not any((media_dir / "attachments").iterdir())
    finally:
        await client.aclose()
        await engine.dispose()


async def test_project_delete_removes_only_its_sessions(tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        await s.flush()
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r1", name="role"))
        s.add(Permission(id="p0", name="projects:delete"))
        await s.flush()
        s.add(RolePermissionLink(role_id="r1", permission_id="p0"))
        await s.flush()
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(Provider(id="prov", name="test", kind="test"))
        await s.flush()
        await s.flush()
        s.add(Model(id="m", provider_id="prov", name="mm"))
        await s.flush()
        await s.flush()
        s.add(Agent(id="ag", name="a", description="", instructions="", model_id="m"))
        await s.flush()
        s.add(Project(id="keep", name="keep", path=".", owner_id="u1"))
        await s.flush()
        s.add(Project(id="gone", name="gone", path=".", owner_id="u1"))
        await s.flush()
        await s.flush()
        s.add(SessionRow(id="s-keep", project_id="keep", agent_id="ag"))
        await s.flush()
        s.add(SessionRow(id="s-gone", project_id="gone", agent_id="ag"))
        await s.flush()
        await s.flush()
        s.add(TurnRow(id="t-keep", session_id="s-keep", role="user", content="hi"))
        await s.flush()
        s.add(TurnRow(id="t-gone", session_id="s-gone", role="user", content="bye"))
        await s.commit()
    app = create_app(
        Settings(jwt_secret="s" * 32, media_dir=str(tmp_path / "media")),
        engine=engine,
        session_factory=factory,
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    try:
        token = (
            await client.post(
                "/auth/login", json={"username": "alice", "password": "pw"}
            )
        ).json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        assert (await client.delete("/projects/gone", headers=h)).status_code == 200
        async with factory() as s:
            assert await s.get(Project, "gone") is None
            assert await s.get(SessionRow, "s-gone") is None
            assert await s.get(TurnRow, "t-gone") is None
            assert await s.get(Project, "keep") is not None
            assert await s.get(SessionRow, "s-keep") is not None
            assert await s.get(TurnRow, "t-keep") is not None
    finally:
        await client.aclose()
        await engine.dispose()
