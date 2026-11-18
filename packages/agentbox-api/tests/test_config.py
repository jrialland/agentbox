from agentbox_api.config import Settings


def test_settings_defaults():
    s = Settings(jwt_secret="secret")
    assert s.database_url == "sqlite+aiosqlite:///./agentbox.db"
    assert s.jwt_algorithm == "HS256"
    assert s.jwt_expiry_seconds == 3600


def test_settings_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "fromenv")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    s = Settings()
    assert s.jwt_secret.get_secret_value() == "fromenv"
    assert s.database_url == "sqlite+aiosqlite:///:memory:"
