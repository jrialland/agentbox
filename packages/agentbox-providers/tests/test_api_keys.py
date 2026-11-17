from agentbox_models.tables.core import Provider
from agentbox_providers.api_keys import resolve_api_key


def test_stored_key_wins():
    p = Provider(id="p", name="moonshot", kind="generic", api_key="stored")
    assert resolve_api_key(p) == "stored"


def test_env_var_fallback(monkeypatch):
    monkeypatch.setenv("MOONSHOT_API_KEY", "envkey")
    p = Provider(id="p", name="moonshot", kind="generic")
    assert resolve_api_key(p) == "envkey"


def test_none_when_no_key(monkeypatch):
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    p = Provider(id="p", name="moonshot", kind="generic")
    assert resolve_api_key(p) is None
