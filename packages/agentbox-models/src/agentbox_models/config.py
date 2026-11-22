from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, Field
from sqlalchemy.engine import URL, make_url

DatabaseVendor = Literal["sqlite", "postgresql", "mysql", "mariadb"]

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./agentbox.db"
DEFAULT_MEDIA_DIR = "./media"
DEFAULT_PORTS = {"postgresql": 5432, "mysql": 3306, "mariadb": 3306}
ASYNC_DRIVERS = {
    "sqlite": "sqlite+aiosqlite",
    "postgresql": "postgresql+asyncpg",
    "mysql": "mysql+aiomysql",
    "mariadb": "mariadb+aiomysql",
}
SYNC_DRIVER_ALIASES = {
    "sqlite": "sqlite+aiosqlite",
    "postgresql": "postgresql+asyncpg",
    "postgres": "postgresql+asyncpg",
    "postgresql+psycopg2": "postgresql+asyncpg",
    "postgresql+psycopg": "postgresql+asyncpg",
    "mysql": "mysql+aiomysql",
    "mysql+pymysql": "mysql+aiomysql",
    "mysql+mysqldb": "mysql+aiomysql",
    "mariadb": "mariadb+aiomysql",
    "mariadb+pymysql": "mariadb+aiomysql",
}
_ASYNC_DRIVERS = {
    "sqlite+aiosqlite",
    "postgresql+asyncpg",
    "mysql+aiomysql",
    "mariadb+aiomysql",
    "mysql+asyncmy",
    "mariadb+asyncmy",
}


class DatabaseSettings(BaseModel):
    vendor: DatabaseVendor = "sqlite"
    path: str | None = None
    host: str | None = None
    port: int | None = None
    name: str | None = None
    user: str | None = None
    password: str | None = None
    url: str | None = None
    params: dict[str, str] = Field(default_factory=dict)


class StorageSettings(BaseModel):
    media_dir: str = DEFAULT_MEDIA_DIR


class AgentboxConfig(BaseModel):
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)


def _environ(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    if environ is not None:
        return {key: value for key, value in environ.items() if value is not None}
    values = {
        key: value for key, value in dotenv_values(".env").items() if value is not None
    }
    values.update(os.environ)
    return values


def config_file_path(environ: Mapping[str, str] | None = None) -> Path | None:
    env = _environ(environ)
    explicit = env.get("AGENTBOX_CONFIG")
    if explicit:
        return Path(explicit)
    default = Path("agentbox.toml")
    return default if default.is_file() else None


def load_config_file(path: Path | str | None = None) -> AgentboxConfig:
    chosen = Path(path) if path is not None else config_file_path()
    if chosen is None:
        return AgentboxConfig()
    data = tomllib.loads(chosen.read_text(encoding="utf-8"))
    return AgentboxConfig.model_validate(data)


def _apply_database_env(
    settings: DatabaseSettings, environ: Mapping[str, str]
) -> DatabaseSettings:
    updates: dict[str, object] = {}
    for env_name, field_name in {
        "DATABASE_VENDOR": "vendor",
        "DATABASE_HOST": "host",
        "DATABASE_USER": "user",
        "DATABASE_PASSWORD": "password",
        "DATABASE_NAME": "name",
        "DATABASE_PATH": "path",
    }.items():
        value = environ.get(env_name)
        if value:
            updates[field_name] = value
    port = environ.get("DATABASE_PORT")
    if port:
        updates["port"] = int(port)
    return settings.model_copy(update=updates)


def resolve_database_settings(
    config: AgentboxConfig | None = None,
    environ: Mapping[str, str] | None = None,
) -> DatabaseSettings:
    env = _environ(environ)
    base = (config or load_config_file()).database
    return _apply_database_env(base, env)


def _mariadb_drivername() -> str:
    from sqlalchemy.dialects import registry

    try:
        registry.load("mariadb+aiomysql")
    except Exception:
        return "mysql+aiomysql"
    return "mariadb+aiomysql"


def build_database_url(database: DatabaseSettings) -> str:
    if database.url:
        return normalize_async_url(database.url)
    if database.vendor == "sqlite":
        return URL.create(
            ASYNC_DRIVERS["sqlite"],
            database=database.path or "./agentbox.db",
        ).render_as_string(hide_password=False)

    drivername = ASYNC_DRIVERS[database.vendor]
    if database.vendor == "mariadb":
        drivername = _mariadb_drivername()
    return URL.create(
        drivername,
        username=database.user,
        password=database.password,
        host=database.host or "localhost",
        port=database.port or DEFAULT_PORTS[database.vendor],
        database=database.name or "agentbox",
        query=database.params,
    ).render_as_string(hide_password=False)


def resolve_database_url(
    config: AgentboxConfig | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    env = _environ(environ)
    explicit = env.get("DATABASE_URL")
    if explicit:
        return normalize_async_url(explicit)
    return build_database_url(resolve_database_settings(config, env))


def resolve_media_dir(
    config: AgentboxConfig | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    env = _environ(environ)
    explicit = env.get("MEDIA_DIR")
    if explicit:
        return explicit
    return (config or load_config_file()).storage.media_dir


def normalize_async_url(database_url: str) -> str:
    parsed = make_url(database_url)
    driver = parsed.drivername.lower()
    if driver in _ASYNC_DRIVERS:
        return database_url
    replacement = SYNC_DRIVER_ALIASES.get(driver)
    if replacement is None:
        return database_url
    return parsed.set(drivername=replacement).render_as_string(hide_password=False)
