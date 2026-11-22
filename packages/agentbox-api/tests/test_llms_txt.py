import re

import httpx
import pytest
import pytest_asyncio

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.routers.llms import SECTION_FILES
from agentbox_models.db import create_engine_and_sessionmaker, init_db

EXPECTED_SECTIONS = [
    "authentication.md",
    "quickstart.md",
    "agents.md",
    "sessions.md",
    "streaming.md",
    "protocols.md",
    "reference.md",
]


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
    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.text.startswith("# ")


@pytest.mark.parametrize("filename", EXPECTED_SECTIONS)
async def test_section_served_without_auth(client, filename):
    response = await client.get(f"/llms/{filename}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text.startswith("# ")


def test_expected_sections_match_router():
    assert set(EXPECTED_SECTIONS) == SECTION_FILES


async def test_index_links_resolve(client):
    index = (await client.get("/llms.txt")).text
    links = set(re.findall(r"\]\((/llms/[^)#]+)\)", index))
    assert links
    for link in sorted(links):
        response = await client.get(link)
        assert response.status_code == 200, link


async def test_unknown_section_is_404(client):
    response = await client.get("/llms/unknown.md")
    assert response.status_code == 404


async def test_llms_routes_absent_from_openapi(client):
    document = (await client.get("/openapi.json")).json()
    assert not any(path.startswith("/llms") for path in document["paths"])
