import httpx
import pytest_asyncio

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_models.db import create_engine_and_sessionmaker, init_db


@pytest_asyncio.fixture
async def client():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    app = create_app(
        Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    await engine.dispose()


async def test_index_served_without_auth(client):
    response = await client.get("/llms.txt")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text.startswith("# ")


async def test_llms_routes_absent_from_openapi(client):
    document = (await client.get("/openapi.json")).json()
    assert not any(path.startswith("/llms") for path in document["paths"])
