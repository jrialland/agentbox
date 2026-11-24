"""Resolve database and storage settings for agentbox.

Configuration is layered. Values loaded from ``.env`` are overridden by the real
process environment; for database settings those environment values in turn
override an optional ``agentbox.toml`` file. A connection string in
``DATABASE_URL`` bypasses the individual database fields entirely. The public
helpers are read-only and safe to call concurrently, and they convert supported
synchronous SQLAlchemy URLs to async drivers for the runtime.
"""

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
    """Per-vendor database connection fields.

    Attributes:
        path: SQLite database file path; ignored for server vendors.
        url: Full SQLAlchemy URL. When set it takes precedence over the
            individual fields and is normalized to an async driver.
        params: Extra query-string parameters appended to a generated URL.
    """

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
    """Filesystem settings for stored media."""

    media_dir: str = DEFAULT_MEDIA_DIR


class AgentboxConfig(BaseModel):
    """Top-level contents of an ``agentbox.toml`` file."""

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)


def _environ(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    # An explicit mapping is authoritative; otherwise ``.env`` values are
    # overlaid by the real process environment so deployment variables win.
    if environ is not None:
        return {key: value for key, value in environ.items() if value is not None}
    values = {
        key: value for key, value in dotenv_values(".env").items() if value is not None
    }
    values.update(os.environ)
    return values


def config_file_path(environ: Mapping[str, str] | None = None) -> Path | None:
    """Return the TOML config path selected by the environment.

    ``AGENTBOX_CONFIG`` wins when set; otherwise ``agentbox.toml`` is used if it
    exists in the current working directory.

    Args:
        environ: Optional environment mapping. When omitted, the real process
            environment values (including those loaded from ``.env``) are read.

    Returns:
        The selected path, or ``None`` when no config file is configured.
    """
    env = _environ(environ)
    explicit = env.get("AGENTBOX_CONFIG")
    if explicit:
        return Path(explicit)
    default = Path("agentbox.toml")
    return default if default.is_file() else None


def load_config_file(path: Path | str | None = None) -> AgentboxConfig:
    """Load an :class:`AgentboxConfig` from a TOML file.

    Missing files are not an error: when no path is given and none is
    discovered, an empty config with default settings is returned.

    Args:
        path: Explicit TOML path. Defaults to :func:`config_file_path`.

    Returns:
        The parsed configuration, or defaults when no file is found.
    """
    chosen = Path(path) if path is not None else config_file_path()
    if chosen is None:
        return AgentboxConfig()
    data = tomllib.loads(chosen.read_text(encoding="utf-8"))
    return AgentboxConfig.model_validate(data)


def _apply_database_env(
    settings: DatabaseSettings, environ: Mapping[str, str]
) -> DatabaseSettings:
    updates: dict[str, object] = {}
    # Only non-empty environment values override the TOML-backed settings.
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
    """Apply ``DATABASE_*`` environment overrides to database settings.

    Environment values take precedence over the TOML-backed ``config``. This
    helper is read-only.

    Args:
        config: Configuration to start from. Loaded from disk when omitted.
        environ: Optional environment mapping; the real environment when
            omitted.

    Returns:
        A copy of the database settings with overrides applied.
    """
    env = _environ(environ)
    base = (config or load_config_file()).database
    return _apply_database_env(base, env)


def _mariadb_drivername() -> str:
    from sqlalchemy.dialects import registry

    # The MariaDB async dialect is optional; fall back to the MySQL-compatible
    # driver when it is not installed so MariaDB URLs still work.
    try:
        registry.load("mariadb+aiomysql")
    except Exception:
        return "mysql+aiomysql"
    return "mariadb+aiomysql"


def build_database_url(database: DatabaseSettings) -> str:
    """Build an async SQLAlchemy URL from per-field database settings.

    A ``database.url`` value short-circuits field-based construction and is only
    normalized to an async driver. Otherwise the vendor selects the driver, and
    omitted server fields fall back to localhost, the vendor's default port, and
    database name ``agentbox``.

    Args:
        database: Database fields to render into a URL.

    Returns:
        A rendered SQLAlchemy URL with the password included.
    """
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
    """Resolve the final async database URL.

    ``DATABASE_URL`` from the environment overrides all other database
    settings. Otherwise the URL is built from :func:`resolve_database_settings`.

    Args:
        config: Base configuration. Loaded from disk when omitted.
        environ: Optional environment mapping; the real environment when
            omitted.

    Returns:
        The resolved SQLAlchemy URL using an async driver.
    """
    env = _environ(environ)
    explicit = env.get("DATABASE_URL")
    if explicit:
        return normalize_async_url(explicit)
    return build_database_url(resolve_database_settings(config, env))


def resolve_media_dir(
    config: AgentboxConfig | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve the media directory path.

    ``MEDIA_DIR`` from the environment overrides the configured storage
    directory.

    Args:
        config: Base configuration. Loaded from disk when omitted.
        environ: Optional environment mapping; the real environment when
            omitted.

    Returns:
        The configured or overridden media directory path.
    """
    env = _environ(environ)
    explicit = env.get("MEDIA_DIR")
    if explicit:
        return explicit
    return (config or load_config_file()).storage.media_dir


def normalize_async_url(database_url: str) -> str:
    """Convert a synchronous SQLAlchemy URL to an async driver URL.

    URLs that already use an async driver are returned unchanged, and unknown
    drivers are left untouched so custom dialects keep working. Known sync
    spellings are rewritten to the bundled async driver.

    Args:
        database_url: SQLAlchemy URL to normalize.

    Returns:
        The normalized URL, with the password preserved.
    """
    parsed = make_url(database_url)
    driver = parsed.drivername.lower()
    if driver in _ASYNC_DRIVERS:
        return database_url
    replacement = SYNC_DRIVER_ALIASES.get(driver)
    if replacement is None:
        return database_url
    return parsed.set(drivername=replacement).render_as_string(hide_password=False)
