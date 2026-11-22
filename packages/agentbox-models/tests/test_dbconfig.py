from pathlib import Path

from agentbox_models.config import (
    AgentboxConfig,
    DatabaseSettings,
    build_database_url,
    config_file_path,
    load_config_file,
    normalize_async_url,
    resolve_database_url,
    resolve_media_dir,
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_sqlite_default():
    assert (
        resolve_database_url(AgentboxConfig(), environ={})
        == "sqlite+aiosqlite:///./agentbox.db"
    )


def test_postgres_url_is_built_and_password_is_escaped():
    config = AgentboxConfig(
        database=DatabaseSettings(
            vendor="postgresql",
            host="db.local",
            port=5432,
            name="agentbox",
            user="agentbox",
            password="p@ss/word",
            params={"ssl": "require"},
        )
    )
    assert (
        build_database_url(config.database)
        == "postgresql+asyncpg://agentbox:p%40ss%2Fword@db.local:5432/agentbox?ssl=require"
    )


def test_mysql_and_mariadb_default_ports():
    assert build_database_url(
        DatabaseSettings(vendor="mysql", name="agentbox", user="u")
    ).startswith("mysql+aiomysql://u@localhost:3306/agentbox")
    assert build_database_url(
        DatabaseSettings(vendor="mariadb", name="agentbox", user="u")
    ).startswith(("mariadb+aiomysql://", "mysql+aiomysql://"))


def test_agentbox_config_env_names_the_file(tmp_path):
    path = _write(tmp_path / "custom.toml", '[database]\nvendor = "sqlite"\n')
    assert config_file_path({"AGENTBOX_CONFIG": str(path)}) == path


def test_toml_is_loaded_from_explicit_path(tmp_path):
    path = _write(
        tmp_path / "agentbox.toml",
        '[database]\nvendor = "sqlite"\npath = "./custom.db"\n'
        '[storage]\nmedia_dir = "./assets"\n',
    )
    config = load_config_file(path)
    assert config.database.path == "./custom.db"
    assert config.storage.media_dir == "./assets"
    assert resolve_media_dir(config, environ={}) == "./assets"


def test_env_overrides_toml():
    config = AgentboxConfig(
        database=DatabaseSettings(vendor="sqlite", path="./file.db")
    )
    environ = {"DATABASE_VENDOR": "postgresql", "DATABASE_HOST": "pg"}
    url = resolve_database_url(config, environ)
    assert url.startswith("postgresql+asyncpg://")


def test_database_url_wins_over_toml():
    config = AgentboxConfig(
        database=DatabaseSettings(vendor="sqlite", path="./file.db")
    )
    assert (
        resolve_database_url(config, {"DATABASE_URL": "sqlite+aiosqlite:///:memory:"})
        == "sqlite+aiosqlite:///:memory:"
    )


def test_normalize_sync_urls():
    assert normalize_async_url("sqlite:///./x.db") == "sqlite+aiosqlite:///./x.db"
    assert (
        normalize_async_url("postgresql://u:p@h/d")
        == "postgresql+asyncpg://u:p@h/d"
    )
    assert normalize_async_url("mysql://u:p@h/d") == "mysql+aiomysql://u:p@h/d"
    assert (
        normalize_async_url("postgresql+psycopg2://u:p@h/d")
        == "postgresql+asyncpg://u:p@h/d"
    )
    assert (
        normalize_async_url("postgresql+asyncpg://u:p@h/d")
        == "postgresql+asyncpg://u:p@h/d"
    )
