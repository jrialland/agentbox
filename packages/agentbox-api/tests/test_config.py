from agentbox_api.config import Settings


def test_settings_defaults():
    s = Settings(jwt_secret="x" * 32)
    assert s.database_url == "sqlite+aiosqlite:///./agentbox.db"
    assert s.jwt_algorithm == "HS256"
    assert s.jwt_expiry_seconds == 3600


def test_settings_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "e" * 32)
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    s = Settings()
    assert s.jwt_secret.get_secret_value() == "e" * 32
    assert s.database_url == "sqlite+aiosqlite:///:memory:"
