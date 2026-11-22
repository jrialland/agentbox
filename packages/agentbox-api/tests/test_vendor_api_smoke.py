import uuid
from io import BytesIO

import httpx
import pytest
from PIL import Image
from sqlmodel import SQLModel

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


@pytest.mark.timeout(180)
async def test_vendor_api_smoke(db_url, tmp_path):
    engine, factory = create_engine_and_sessionmaker(db_url)
    await init_db(engine)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)

    suffix = uuid.uuid4().hex[:8]
    async with factory() as s:
        s.add(
            User(
                id=f"u{suffix}",
                username="alice",
                email="a@x",
                password_hash=hash_password("pw"),
            )
        )
        s.add(Role(id=f"r{suffix}", name="role"))
        for index, name in enumerate(
            [
                "agents:create",
                "agents:read",
                "agents:delete",
                "api_keys:manage",
                "sessions:create",
                "sessions:read",
            ]
        ):
            s.add(Permission(id=f"p{index}{suffix}", name=name))
        await s.flush()
        for index in range(6):
            s.add(
                RolePermissionLink(
                    role_id=f"r{suffix}", permission_id=f"p{index}{suffix}"
                )
            )
        s.add(UserRoleLink(user_id=f"u{suffix}", role_id=f"r{suffix}"))
        s.add(Provider(id=f"pr{suffix}", name="test", kind="generic"))
        await s.flush()
        s.add(Model(id=f"m{suffix}", provider_id=f"pr{suffix}", name="test-model"))
        await s.flush()
        s.add(
            Agent(
                id=f"a{suffix}",
                name=f"bot-{suffix}",
                description="",
                instructions="",
                model_id=f"m{suffix}",
                created_by=f"u{suffix}",
            )
        )
        s.add(
            Project(
                id=f"pjr{suffix}",
                name="p",
                path=str(tmp_path),
                owner_id=f"u{suffix}",
            )
        )
        await s.flush()
        s.add(
            SessionRow(
                id=f"s{suffix}",
                project_id=f"pjr{suffix}",
                agent_id=f"a{suffix}",
            )
        )
        await s.commit()

    app = create_app(
        Settings(
            jwt_secret="s" * 32,
            database_url=db_url,
            media_dir=str(tmp_path / "media"),
        ),
        engine=engine,
        session_factory=factory,
    )
    png = BytesIO()
    Image.new("RGB", (32, 32), "red").save(png, format="PNG")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/auth/login", json={"username": "alice", "password": "pw"}
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        spec = await client.post(
            "/agents",
            json={
                "name": f"coder-{suffix}",
                "model": "test-model",
                "tool_bindings": [{"name": "write_file", "required_flags": ["write"]}],
                "mode_definitions": [{"name": "agent", "flags": {"write": True}}],
            },
            headers=headers,
        )
        assert spec.status_code == 200

        api_key = await client.post(
            "/api-keys", json={"scopes": ["agents:read"]}, headers=headers
        )
        assert api_key.status_code == 200
        assert api_key.json()["scopes"] == ["agents:read"]

        card_body = {
            "name": "Bot",
            "description": "d",
            "version": "1.0.0",
            "skills": [],
        }
        card = await client.put(
            f"/agents/bot-{suffix}/card", json=card_body, headers=headers
        )
        assert card.status_code == 200
        card_read = await client.get(f"/agents/bot-{suffix}/card", headers=headers)
        assert card_read.status_code == 200
        assert card_read.json()["name"] == "Bot"

        avatar = await client.put(
            f"/agents/bot-{suffix}/avatar",
            files={"file": ("a.png", png.getvalue(), "image/png")},
            headers=headers,
        )
        assert avatar.status_code == 204
        avatar_read = await client.get(f"/agents/bot-{suffix}/avatar")
        assert avatar_read.status_code == 200
        assert avatar_read.headers["content-type"].startswith("image/png")

        upload = await client.post(
            f"/sessions/s{suffix}/attachments",
            files={"file": ("note.txt", b"hello", "text/plain")},
            headers=headers,
        )
        assert upload.status_code == 200
        attachment_id = upload.json()["id"]
        download = await client.get(
            f"/sessions/s{suffix}/attachments/{attachment_id}", headers=headers
        )
        assert download.status_code == 200 and download.content == b"hello"

        attachments_dir = tmp_path / "media" / "attachments"
        avatars_dir = tmp_path / "media" / "avatars"
        cards_dir = tmp_path / "media" / "agent-cards"
        assert any(attachments_dir.iterdir())
        assert any(avatars_dir.iterdir())
        assert any(cards_dir.iterdir())

        deleted = await client.delete(f"/sessions/s{suffix}", headers=headers)
        assert deleted.status_code == 200
        assert not any(attachments_dir.iterdir())

        deleted_agent = await client.delete(f"/agents/bot-{suffix}", headers=headers)
        assert deleted_agent.status_code == 200
        assert not any(avatars_dir.iterdir())
        assert not any(cards_dir.iterdir())

    await engine.dispose()
