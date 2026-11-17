from agentbox_models.tables.core import Provider
from agentbox_providers.models import list_models


async def test_list_models_parses_ids(monkeypatch):
    captured = {}

    async def fake_get(url, headers=None):
        captured["url"] = url
        captured["headers"] = headers
        return {
            "object": "list",
            "data": [{"id": "moonshot-v1-8k"}, {"id": "moonshot-v1-32k"}],
        }

    monkeypatch.setattr("agentbox_providers.models._get_json", fake_get)
    p = Provider(
        id="p",
        name="moonshot",
        kind="generic",
        models_url="https://api.moonshot.cn/v1/models",
        api_key="sk-test",
    )
    assert await list_models(p) == ["moonshot-v1-8k", "moonshot-v1-32k"]
    assert captured["url"] == "https://api.moonshot.cn/v1/models"
    assert captured["headers"] == {"Authorization": "Bearer sk-test"}
