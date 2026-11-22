from agentbox_api.config import Settings


def test_settings_reads_toml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENTBOX_CONFIG", raising=False)
    (tmp_path / "agentbox.toml").write_text(
        '[database]\nvendor = "sqlite"\npath = "./from-toml.db"\n'
        '[storage]\nmedia_dir = "./from-toml-media"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.delenv("MEDIA_DIR", raising=False)
    settings = Settings(jwt_secret="s" * 32)
    assert settings.database_url == "sqlite+aiosqlite:///./from-toml.db"
    assert settings.media_dir == "./from-toml-media"


def test_database_url_env_wins(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENTBOX_CONFIG", raising=False)
    (tmp_path / "agentbox.toml").write_text(
        '[database]\nvendor = "postgresql"\nhost = "pg"\nname = "agentbox"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    assert Settings(jwt_secret="s" * 32).database_url == "sqlite+aiosqlite:///:memory:"


def test_explicit_constructor_wins(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENTBOX_CONFIG", raising=False)
    (tmp_path / "agentbox.toml").write_text(
        '[database]\nvendor = "postgresql"\nhost = "pg"\nname = "agentbox"\n',
        encoding="utf-8",
    )
    settings = Settings(
        jwt_secret="s" * 32,
        database_url="sqlite+aiosqlite:///:memory:",
        media_dir=str(tmp_path / "media"),
    )
    assert settings.database_url == "sqlite+aiosqlite:///:memory:"
    assert settings.media_dir == str(tmp_path / "media")
