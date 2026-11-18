"""Tests for the MCP App sandbox page + CSP."""

import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.sandbox import csp_header
from agentbox_models.db import create_engine_and_sessionmaker, init_db


async def _client(tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    app = create_app(
        Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    return engine, client


async def test_sandbox_page_served_with_csp(tmp_path):
    engine, client = await _client(tmp_path)
    try:
        r = await client.get("/sandbox")
        assert r.status_code == 200
        assert "Content-Security-Policy" in r.headers
        assert "sandbox-proxy-ready" in r.text
    finally:
        await client.aclose()
        await engine.dispose()


def test_csp_header_defaults():
    header = csp_header(None)
    assert "default-src 'none'" in header
    assert "connect-src 'none'" in header


def test_csp_header_honours_meta():
    header = csp_header('{"connectDomains":["https://api.example.com"]}')
    assert "connect-src https://api.example.com" in header
