import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings


async def test_app_health():
    app = create_app(Settings(jwt_secret="s" * 32))

    @app.get("/health")
    async def health():
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"ok": True}


async def test_app_has_session_factory():
    app = create_app(Settings(jwt_secret="s" * 32))
    assert app.state.session_factory is not None
    assert app.state.settings is not None
