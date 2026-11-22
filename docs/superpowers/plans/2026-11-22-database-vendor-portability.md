# Database Vendor Portability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the schema-v1 application selectable across SQLite, PostgreSQL 16, MySQL 8, and MariaDB 11 through `agentbox.toml` plus environment overrides, with a testcontainers conformance suite.

**Architecture:** A shared TOML/env resolver in `agentbox-models` builds SQLAlchemy async URLs for the app and Alembic. The engine normalizes sync URLs and keeps the SQLite FK pragma. Alembic detects async URLs and runs migrations through an async engine. Root-level pytest fixtures start one container per vendor and skip unless Docker is available.

**Tech Stack:** Python 3.11, SQLModel/SQLAlchemy 2 async, alembic, asyncpg, aiomysql, aiosqlite, python-dotenv, testcontainers, pytest/pytest-asyncio.

## Global Constraints

- SQLite remains the default when no configuration file is present.
- `DATABASE_URL` and environment variables override `agentbox.toml`.
- Supported vendors: `sqlite`, `postgresql`, `mysql`, `mariadb`.
- PostgreSQL driver is `asyncpg`; MySQL/MariaDB driver is `aiomysql`.
- No sync PostgreSQL/MySQL driver dependency; Alembic uses the async engine.
- `agentbox.toml` is optional and must not change behavior when absent.
- Container images: `postgres:16`, `mysql:8.0`, `mariadb:11`.
- Container tests skip when Docker is unavailable; `AGENTBOX_SKIP_CONTAINERS=1` forces skip.
- Keep `pytest-timeout` `timeout = 60` in package config; only container-dependent tests override it.
- Do not pass multiple package test directories to one pytest run.
- Ruff line length 100; target Python 3.11.
- Every task ends with a commit.

---

## File Structure

**New files**

- `packages/agentbox-models/src/agentbox_models/config.py` — TOML/env database and storage resolution.
- `packages/agentbox-models/tests/test_dbconfig.py` — resolver tests.
- `packages/agentbox-api/tests/test_settings_config.py` — `Settings` integration tests.
- `conftest.py` (repo root) — Docker/container fixtures.
- `packages/agentbox-models/tests/conftest.py` — `db_url` vendor-parameterized fixture.
- `packages/agentbox-models/tests/test_vendor_schema.py` — model conformance.
- `packages/agentbox-models/tests/test_vendor_migrations.py` — migration conformance.
- `packages/agentbox-api/tests/test_vendor_api_smoke.py` — API smoke per vendor.
- `agentbox.example.toml` — documented example config.

**Rewritten files**

- `packages/agentbox-models/src/agentbox_models/db.py` — URL normalization and `pool_pre_ping`.
- `packages/agentbox-api/src/agentbox_api/config.py` — resolver-backed `database_url`/`media_dir`.
- `packages/agentbox-models/alembic/env.py` — async/TOML-aware migrations.
- `packages/agentbox-models/alembic.ini` — no hard-coded URL.
- `packages/agentbox-models/pyproject.toml` — drivers and dotenv.
- `pyproject.toml` — testcontainers dev dependency.
- `justfile` — reset-db recipe.
- `AGENTS.md`, `README.md`, architecture docs, `docs/ROADMAP.md`.

**Modified tests**

- `packages/agentbox-api/tests/conftest.py` — `db_url` fixture.
- `packages/agentbox-api/tests/test_config.py` — resolver-backed defaults.
- `packages/agentbox-models/tests/test_initial_schema.py` — async URL coverage.

---

## Task 1: Dependencies and example config

**Files:**
- Modify: `packages/agentbox-models/pyproject.toml`
- Modify: `pyproject.toml`
- Create: `agentbox.example.toml`
- Modify: `.gitignore`
- Modify: `uv.lock` (via `uv lock`)

**Interfaces:**
- Produces installed modules: `asyncpg`, `aiomysql`, `dotenv`, `testcontainers`.

- [ ] **Step 1: Add model runtime dependencies**

In `packages/agentbox-models/pyproject.toml` dependencies add:

```toml
    "asyncpg>=0.29",
    "aiomysql>=0.2",
    "python-dotenv>=1.0",
```

- [ ] **Step 2: Add testcontainers to root dev dependencies**

In `pyproject.toml` `[dependency-groups].dev` add:

```toml
    "testcontainers[postgres,mysql,mariadb]>=4.8",
```

- [ ] **Step 3: Add the example config**

Create `agentbox.example.toml`:

```toml
# Copy to agentbox.toml to select a database vendor.
# Environment variables override these values.

[database]
vendor = "sqlite"          # sqlite | postgresql | mysql | mariadb
path = "./agentbox.db"     # sqlite only

# PostgreSQL example:
# vendor = "postgresql"
# host = "localhost"
# port = 5432
# name = "agentbox"
# user = "agentbox"
# password = ""            # prefer DATABASE_PASSWORD in the environment
# params = { ssl = "require" }

# MySQL example:
# vendor = "mysql"
# host = "localhost"
# port = 3306
# name = "agentbox"
# user = "agentbox"

# MariaDB example:
# vendor = "mariadb"
# host = "localhost"
# port = 3306
# name = "agentbox"
# user = "agentbox"

# Full URL escape hatch:
# url = "postgresql+asyncpg://agentbox:secret@localhost:5432/agentbox"

[storage]
media_dir = "./media"
```

- [ ] **Step 4: Ignore the default media directory**

Add to `.gitignore`:

```text
/media/
/e2e-media/
```

- [ ] **Step 5: Sync dependencies**

```powershell
uv lock
uv sync
```

Expected: `asyncpg`, `aiomysql`, `python-dotenv`, and `testcontainers` resolve; no sync Postgres/MySQL driver is required.

- [ ] **Step 6: Commit**

```powershell
git add packages/agentbox-models/pyproject.toml pyproject.toml uv.lock agentbox.example.toml .gitignore
git commit -m "chore: add database drivers and container test dependencies"
```

---

## Task 2: Shared database configuration resolver

**Files:**
- Create: `packages/agentbox-models/src/agentbox_models/config.py`
- Test: `packages/agentbox-models/tests/test_dbconfig.py`

**Interfaces:**
- Produces: `DatabaseSettings`, `StorageSettings`, `AgentboxConfig`
- Produces: `config_file_path(environ=None) -> Path | None`
- Produces: `load_config_file(path=None) -> AgentboxConfig`
- Produces: `resolve_database_settings(config=None, environ=None) -> DatabaseSettings`
- Produces: `build_database_url(settings) -> str`
- Produces: `resolve_database_url(config=None, environ=None) -> str`
- Produces: `resolve_media_dir(config=None, environ=None) -> str`
- Produces: `normalize_async_url(url) -> str`

- [ ] **Step 1: Write failing resolver tests**

```python
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
    ).startswith("mariadb+aiomysql://u@localhost:3306/agentbox")


def test_agentbox_config_env_names_the_file(tmp_path):
    path = _write(tmp_path / "custom.toml", "[database]\nvendor = \"sqlite\"\n")
    assert config_file_path({"AGENTBOX_CONFIG": str(path)}) == path


def test_toml_is_loaded_from_explicit_path(tmp_path):
    path = _write(
        tmp_path / "agentbox.toml",
        '[database]\nvendor = "sqlite"\npath = "./custom.db"\n[storage]\nmedia_dir = "./assets"\n',
    )
    config = load_config_file(path)
    assert config.database.path == "./custom.db"
    assert config.storage.media_dir == "./assets"
    assert resolve_media_dir(config, environ={}) == "./assets"


def test_env_overrides_toml():
    config = AgentboxConfig(database=DatabaseSettings(vendor="sqlite", path="./file.db"))
    environ = {"DATABASE_VENDOR": "postgresql", "DATABASE_HOST": "pg"}
    url = resolve_database_url(config, environ)
    assert url.startswith("postgresql+asyncpg://")


def test_database_url_wins_over_toml():
    config = AgentboxConfig(database=DatabaseSettings(vendor="sqlite", path="./file.db"))
    assert (
        resolve_database_url(config, {"DATABASE_URL": "sqlite+aiosqlite:///:memory:"})
        == "sqlite+aiosqlite:///:memory:"
    )


def test_normalize_sync_urls():
    assert normalize_async_url("sqlite:///./x.db") == "sqlite+aiosqlite:///./x.db"
    assert normalize_async_url("postgresql://u:p@h/d") == "postgresql+asyncpg://u:p@h/d"
    assert normalize_async_url("mysql://u:p@h/d") == "mysql+aiomysql://u:p@h/d"
    assert (
        normalize_async_url("postgresql+psycopg2://u:p@h/d")
        == "postgresql+asyncpg://u:p@h/d"
    )
    assert normalize_async_url("postgresql+asyncpg://u:p@h/d") == "postgresql+asyncpg://u:p@h/d"
```

Note: `resolve_database_url` returns a string; the env-precedence test above should call `resolve_database_url(config, environ)` and assert the returned string, not reuse the name `settings`.

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest packages/agentbox-models/tests/test_dbconfig.py -q`
Expected: FAIL with `ModuleNotFoundError: agentbox_models.config`.

- [ ] **Step 3: Implement `config.py`**

```python
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
    values = {key: value for key, value in dotenv_values(".env").items() if value is not None}
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
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest packages/agentbox-models/tests/test_dbconfig.py -q`
Expected: PASS. If the MariaDB dialect is unavailable, the test expects `mariadb+aiomysql`; install the dependency from Task 1 before running.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-models/src/agentbox_models/config.py packages/agentbox-models/tests/test_dbconfig.py
git commit -m "feat(models): add toml and env database configuration resolver"
```

---

## Task 3: Resolver-backed `Settings`

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/config.py`
- Test: `packages/agentbox-api/tests/test_config.py`
- Test: `packages/agentbox-api/tests/test_settings_config.py`

**Interfaces:**
- Preserves `Settings().database_url: str` after validation.
- Adds `Settings().media_dir: str` after validation.
- Keeps explicit constructor arguments (`Settings(database_url=...)`, `Settings(media_dir=...)`).

- [ ] **Step 1: Write failing Settings tests**

```python
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
```

Update `test_config.py` default assertion to keep `sqlite+aiosqlite:///./agentbox.db`; it should still pass.

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-api/tests/test_config.py packages/agentbox-api/tests/test_settings_config.py -q`
Expected: FAIL because TOML is ignored and `database_url` is always defaulted.

- [ ] **Step 3: Update `Settings`**

```python
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from agentbox_models.config import (
    load_config_file,
    resolve_database_url,
    resolve_media_dir,
)


class Settings(BaseSettings):
    database_url: str | None = None
    media_dir: str | None = None
    jwt_secret: SecretStr = Field(min_length=32)
    # ... keep every existing field unchanged ...
    model_config = SettingsConfigDict(env_file=".env")

    @model_validator(mode="after")
    def _resolve_paths(self):
        config = load_config_file()
        if not self.database_url:
            self.database_url = resolve_database_url(config)
        if not self.media_dir:
            self.media_dir = resolve_media_dir(config)
        return self
```

Do not change other fields or their defaults.

- [ ] **Step 4: Run tests**

Run: `uv run pytest packages/agentbox-api/tests/test_config.py packages/agentbox-api/tests/test_settings_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-api/src/agentbox_api/config.py packages/agentbox-api/tests/test_config.py packages/agentbox-api/tests/test_settings_config.py
git commit -m "feat(api): resolve database and media config from toml and env"
```

---

## Task 4: Async URL normalization in the engine factory

**Files:**
- Modify: `packages/agentbox-models/src/agentbox_models/db.py`
- Test: `packages/agentbox-models/tests/test_db.py`

**Interfaces:**
- `create_engine_and_sessionmaker(database_url, echo=False)` always creates an async engine from a sync or async URL.

- [ ] **Step 1: Write failing engine test**

```python
from agentbox_models.db import create_engine_and_sessionmaker


async def test_engine_factory_normalizes_sync_url(tmp_path):
    db = tmp_path / "sync.db"
    engine, factory = create_engine_and_sessionmaker(f"sqlite:///{db.as_posix()}")
    assert engine.url.drivername == "sqlite+aiosqlite"
    await engine.dispose()


async def test_engine_factory_keeps_async_url(tmp_path):
    engine, _ = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    assert engine.url.drivername == "sqlite+aiosqlite"
    await engine.dispose()
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-models/tests/test_db.py -q`
Expected: FAIL because `sqlite:///` is not an async driver.

- [ ] **Step 3: Implement normalization**

```python
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from agentbox_models.config import normalize_async_url


def create_engine_and_sessionmaker(database_url: str, echo: bool = False):
    url = normalize_async_url(database_url)
    engine = create_async_engine(url, echo=echo, pool_pre_ping=True)
    if url.startswith("sqlite"):
        @event.listens_for(engine.sync_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest packages/agentbox-models/tests/test_db.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-models/src/agentbox_models/db.py packages/agentbox-models/tests/test_db.py
git commit -m "feat(models): normalize async database urls in engine factory"
```

---

## Task 5: Async, config-aware Alembic

**Files:**
- Rewrite: `packages/agentbox-models/alembic/env.py`
- Modify: `packages/agentbox-models/alembic.ini`
- Test: `packages/agentbox-models/tests/test_initial_schema.py`

**Interfaces:**
- `alembic upgrade head` resolves `sqlalchemy.url` option first, then `DATABASE_URL`/TOML.
- Async URLs use an async engine; sync URLs use a sync engine.

- [ ] **Step 1: Remove the hard-coded URL**

Set `alembic.ini`:

```ini
sqlalchemy.url =
```

- [ ] **Step 2: Add an async migration test**

Append to `packages/agentbox-models/tests/test_initial_schema.py`:

```python
def test_initial_schema_with_async_sqlite_url(tmp_path):
    db = tmp_path / "async-mig.db"
    config = Config("packages/agentbox-models/alembic.ini")
    config.set_main_option("script_location", "packages/agentbox-models/alembic")
    config.set_main_option(
        "sqlalchemy.url", f"sqlite+aiosqlite:///{db.as_posix()}"
    )
    command.upgrade(config, "head")
    assert db.exists()
    command.downgrade(config, "base")
```

- [ ] **Step 3: Run and verify failure**

Run: `uv run pytest packages/agentbox-models/tests/test_initial_schema.py::test_initial_schema_with_async_sqlite_url -q`
Expected: FAIL because `env.py` uses `engine_from_config` with an async URL.

- [ ] **Step 4: Rewrite `alembic/env.py`**

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

import agentbox_models.tables  # noqa: F401
from agentbox_models.config import resolve_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or resolve_database_url()


def _run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations(url: str) -> None:
    engine = create_async_engine(url, poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    url = _database_url()
    if make_url(url).get_dialect().is_async:
        asyncio.run(_run_async_migrations(url))
        return

    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        _run_migrations(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 5: Run migration tests**

Run: `uv run pytest packages/agentbox-models/tests/test_initial_schema.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add packages/agentbox-models/alembic/env.py packages/agentbox-models/alembic.ini packages/agentbox-models/tests/test_initial_schema.py
git commit -m "feat(models): run alembic migrations from shared config and async urls"
```

---

## Task 6: Testcontainers fixtures

**Files:**
- Create: `conftest.py` (repo root)
- Create: `packages/agentbox-models/tests/conftest.py`
- Modify: `packages/agentbox-api/tests/conftest.py`

**Interfaces:**
- Produces session-scoped fixtures: `postgres_url`, `mysql_url`, `mariadb_url`
- Produces function-scoped fixture: `db_url` (params: `sqlite`, `postgresql`, `mysql`, `mariadb`)

- [ ] **Step 1: Create root `conftest.py`**

```python
import os
from functools import lru_cache

import pytest


@lru_cache(maxsize=1)
def _docker_available() -> bool:
    if os.environ.get("AGENTBOX_SKIP_CONTAINERS") == "1":
        return False
    try:
        from testcontainers.core.docker_client import DockerClient

        return bool(DockerClient().client.ping())
    except Exception:
        return False


def _require_docker() -> None:
    if not _docker_available():
        pytest.skip("Docker unavailable for database container tests")


@pytest.fixture(scope="session")
def postgres_url():
    _require_docker()
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer(
        "postgres:16", username="agentbox", password="agentbox", dbname="agentbox"
    ) as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5432)
        yield f"postgresql+asyncpg://agentbox:agentbox@{host}:{port}/agentbox"


@pytest.fixture(scope="session")
def mysql_url():
    _require_docker()
    from testcontainers.mysql import MySqlContainer

    with MySqlContainer(
        "mysql:8.0",
        username="agentbox",
        password="agentbox",
        database="agentbox",
        root_password="root",
    ) as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(3306)
        yield f"mysql+aiomysql://agentbox:agentbox@{host}:{port}/agentbox"


@pytest.fixture(scope="session")
def mariadb_url():
    _require_docker()
    from testcontainers.mariadb import MariaDBContainer

    with MariaDBContainer(
        "mariadb:11",
        username="agentbox",
        password="agentbox",
        database="agentbox",
        root_password="root",
    ) as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(3306)
        yield f"mariadb+aiomysql://agentbox:agentbox@{host}:{port}/agentbox"
```

- [ ] **Step 2: Create models `conftest.py`**

```python
import pytest


@pytest.fixture(params=["sqlite", "postgresql", "mysql", "mariadb"])
def db_url(request):
    if request.param == "sqlite":
        return "sqlite+aiosqlite:///:memory:"
    return request.getfixturevalue(f"{request.param}_url")
```

- [ ] **Step 3: Add the same `db_url` fixture to API `conftest.py`**

Append:

```python
@pytest.fixture(params=["sqlite", "postgresql", "mysql", "mariadb"])
def db_url(request):
    if request.param == "sqlite":
        return "sqlite+aiosqlite:///:memory:"
    return request.getfixturevalue(f"{request.param}_url")
```

- [ ] **Step 4: Verify collection without starting containers**

Run: `uv run pytest packages/agentbox-models/tests/test_db.py -q`
Expected: PASS; no container starts because `db_url` is not requested.

- [ ] **Step 5: Commit**

```powershell
git add conftest.py packages/agentbox-models/tests/conftest.py packages/agentbox-api/tests/conftest.py
git commit -m "test: add testcontainers fixtures for database vendors"
```

---

## Task 7: Model conformance across vendors

**Files:**
- Create: `packages/agentbox-models/tests/test_vendor_schema.py`
- Create: `packages/agentbox-models/tests/test_vendor_migrations.py`

**Interfaces:**
- Uses `db_url` and container fixtures.
- No production interfaces change.

- [ ] **Step 1: Write the vendor schema test**

```python
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel

from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.repos.project_roots import load_extra_roots, replace_extra_roots
from agentbox_models.tables.auth import User
from agentbox_models.tables.core import (
    Agent,
    Model,
    Project,
    Provider,
    SessionRow,
    TurnRow,
)


async def _reset(engine):
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)


@pytest.mark.timeout(180)
async def test_vendor_roundtrip_and_cascade(db_url):
    engine, factory = create_engine_and_sessionmaker(db_url)
    await init_db(engine)
    await _reset(engine)
    suffix = uuid.uuid4().hex[:8]
    long_text = ("é" * 300) + ("x" * 300)

    async with factory() as s:
        s.add(User(id=f"u{suffix}", username=f"u{suffix}", email="e@x", password_hash="h"))
        s.add(Provider(id=f"p{suffix}", name="test", kind="generic"))
        s.add(Model(id=f"m{suffix}", provider_id=f"p{suffix}", name="test-model"))
        s.add(
            Agent(
                id=f"a{suffix}",
                name=f"agent-{suffix}",
                description=long_text,
                instructions=long_text,
                model_id=f"m{suffix}",
                created_by=f"u{suffix}",
            )
        )
        s.add(
            Project(
                id=f"pr{suffix}",
                name="p",
                path="/tmp/" + long_text,
                owner_id=f"u{suffix}",
            )
        )
        s.add(
            SessionRow(
                id=f"s{suffix}",
                project_id=f"pr{suffix}",
                agent_id=f"a{suffix}",
            )
        )
        await s.commit()

    async with factory() as s:
        await replace_extra_roots(s, f"pr{suffix}", ["/tmp/a", "/tmp/b"])
        await s.commit()
        assert await load_extra_roots(s, f"pr{suffix}") == ["/tmp/a", "/tmp/b"]
        agent = await s.get(Agent, f"a{suffix}")
        assert agent.description == long_text
        assert agent.instructions == long_text
        project = await s.get(Project, f"pr{suffix}")
        assert project.path == "/tmp/" + long_text

        s.add(
            TurnRow(
                id=f"t{suffix}",
                session_id=f"s{suffix}",
                role="user",
                content=long_text,
            )
        )
        await s.commit()

    with pytest.raises(IntegrityError):
        async with factory() as s:
            s.add(
                SessionRow(
                    id=f"bad{suffix}",
                    project_id="missing",
                    agent_id="missing",
                )
            )
            await s.commit()

    async with factory() as s:
        session = await s.get(SessionRow, f"s{suffix}")
        await s.delete(session)
        await s.commit()
        assert await s.get(TurnRow, f"t{suffix}") is None

    await engine.dispose()
```

- [ ] **Step 2: Write the vendor migration test**

```python
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel


def _config(url: str) -> Config:
    config = Config("packages/agentbox-models/alembic.ini")
    config.set_main_option("script_location", "packages/agentbox-models/alembic")
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.mark.parametrize("vendor", ["postgresql", "mysql", "mariadb"])
@pytest.mark.timeout(180)
def test_migrations_on_container_vendor(request, vendor):
    url = request.getfixturevalue(f"{vendor}_url")
    config = _config(url)

    import asyncio

    async def reset():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
        await engine.dispose()

    asyncio.run(reset())
    command.upgrade(config, "head")
    command.downgrade(config, "base")
```

- [ ] **Step 3: Run the SQLite case first**

Run: `uv run pytest "packages/agentbox-models/tests/test_vendor_schema.py::test_vendor_roundtrip_and_cascade[sqlite]" -q`
Expected: PASS.

- [ ] **Step 4: Run container cases**

Run: `uv run pytest packages/agentbox-models/tests/test_vendor_schema.py packages/agentbox-models/tests/test_vendor_migrations.py -q`
Expected: PASS or skip if Docker is unavailable. With Docker running, all vendor cases must pass.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-models/tests/test_vendor_schema.py packages/agentbox-models/tests/test_vendor_migrations.py
git commit -m "test(models): add cross-vendor schema and migration conformance"
```

---

## Task 8: API smoke conformance across vendors

**Files:**
- Create: `packages/agentbox-api/tests/test_vendor_api_smoke.py`

**Interfaces:**
- Uses `db_url`, `tmp_path`.
- No production changes expected; fix any vendor-specific bugs found.

- [ ] **Step 1: Write the smoke test**

```python
import uuid
from io import BytesIO

import httpx
import pytest
from PIL import Image
from sqlmodel import SQLModel

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import (
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)
from agentbox_models.tables.core import Agent, Model, Project, Provider, SessionRow


@pytest.mark.timeout(180)
async def test_vendor_api_smoke(db_url, tmp_path):
    engine, factory = create_engine_and_sessionmaker(db_url)
    await init_db(engine)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)

    suffix = uuid.uuid4().hex[:8]
    async with factory() as s:
        s.add(User(id=f"u{suffix}", username="alice", email="a@x", password_hash=hash_password("pw")))
        s.add(Role(id=f"r{suffix}", name="role"))
        for index, name in enumerate(
            [
                "agents:create",
                "agents:read",
                "agents:delete",
                "api_keys:manage",
                "sessions:create",
                "sessions:read",
            ]
        ):
            s.add(Permission(id=f"p{index}{suffix}", name=name))
            s.add(
                RolePermissionLink(
                    role_id=f"r{suffix}", permission_id=f"p{index}{suffix}"
                )
            )
        s.add(UserRoleLink(user_id=f"u{suffix}", role_id=f"r{suffix}"))
        s.add(Provider(id=f"pr{suffix}", name="test", kind="generic"))
        s.add(Model(id=f"m{suffix}", provider_id=f"pr{suffix}", name="test-model"))
        s.add(
            Agent(
                id=f"a{suffix}",
                name=f"bot-{suffix}",
                description="",
                instructions="",
                model_id=f"m{suffix}",
                created_by=f"u{suffix}",
            )
        )
        s.add(
            Project(
                id=f"pjr{suffix}",
                name="p",
                path=str(tmp_path),
                owner_id=f"u{suffix}",
            )
        )
        s.add(
            SessionRow(
                id=f"s{suffix}",
                project_id=f"pjr{suffix}",
                agent_id=f"a{suffix}",
            )
        )
        await s.commit()

    app = create_app(
        Settings(jwt_secret="s" * 32, database_url=db_url, media_dir=str(tmp_path / "media")),
        engine=engine,
        session_factory=factory,
    )
    png = BytesIO()
    Image.new("RGB", (32, 32), "red").save(png, format="PNG")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        spec = await client.post(
            "/agents",
            json={
                "name": f"coder-{suffix}",
                "model": "test-model",
                "tool_bindings": [{"name": "write_file", "required_flags": ["write"]}],
                "mode_definitions": [{"name": "agent", "flags": {"write": True}}],
            },
            headers=headers,
        )
        assert spec.status_code == 200

        api_key = await client.post(
            "/api-keys", json={"scopes": ["agents:read"]}, headers=headers
        )
        assert api_key.status_code == 200
        assert api_key.json()["scopes"] == ["agents:read"]

        card_body = {"name": "Bot", "description": "d", "version": "1.0.0", "skills": []}
        card = await client.put(
            f"/agents/bot-{suffix}/card", json=card_body, headers=headers
        )
        assert card.status_code == 200
        card_read = await client.get(f"/agents/bot-{suffix}/card", headers=headers)
        assert card_read.status_code == 200
        assert card_read.json()["name"] == "Bot"

        avatar = await client.put(
            f"/agents/bot-{suffix}/avatar",
            files={"file": ("a.png", png.getvalue(), "image/png")},
            headers=headers,
        )
        assert avatar.status_code == 204
        avatar_read = await client.get(f"/agents/bot-{suffix}/avatar")
        assert avatar_read.status_code == 200
        assert avatar_read.headers["content-type"].startswith("image/png")

        upload = await client.post(
            f"/sessions/s{suffix}/attachments",
            files={"file": ("note.txt", b"hello", "text/plain")},
            headers=headers,
        )
        assert upload.status_code == 200
        attachment_id = upload.json()["id"]
        download = await client.get(
            f"/sessions/s{suffix}/attachments/{attachment_id}", headers=headers
        )
        assert download.status_code == 200 and download.content == b"hello"

        attachments_dir = tmp_path / "media" / "attachments"
        avatars_dir = tmp_path / "media" / "avatars"
        cards_dir = tmp_path / "media" / "agent-cards"
        assert any(attachments_dir.iterdir())
        assert any(avatars_dir.iterdir())
        assert any(cards_dir.iterdir())

        deleted = await client.delete(f"/sessions/s{suffix}", headers=headers)
        assert deleted.status_code == 200
        assert not any(attachments_dir.iterdir())

        deleted_agent = await client.delete(f"/agents/bot-{suffix}", headers=headers)
        assert deleted_agent.status_code == 200
        assert not any(avatars_dir.iterdir())
        assert not any(cards_dir.iterdir())

    await engine.dispose()
```

- [ ] **Step 2: Run SQLite case**

Run: `uv run pytest "packages/agentbox-api/tests/test_vendor_api_smoke.py::test_vendor_api_smoke[sqlite]" -q`
Expected: PASS.

- [ ] **Step 3: Run all vendor cases**

Run: `uv run pytest packages/agentbox-api/tests/test_vendor_api_smoke.py -q`
Expected: PASS or skip without Docker. With Docker, all vendors pass.

- [ ] **Step 4: Commit**

```powershell
git add packages/agentbox-api/tests/test_vendor_api_smoke.py
git commit -m "test(api): add cross-vendor api smoke test"
```

---

## Task 9: Developer workflow and docs

**Files:**
- Modify: `justfile`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/architecture/01-system-overview.md`
- Modify: `docs/architecture/02-tech-stack.md`
- Modify: `docs/architecture/03-backend.md`
- Modify: `docs/architecture/05-data-model.md`
- Modify: `docs/architecture/09-chat-and-streaming.md`
- Modify: `docs/architecture/12-glossary-and-decisions.md`
- Modify: `docs/ROADMAP.md`
- Modify: `apps/web/playwright.config.ts`
- Modify: `apps/web/e2e/prepare.ts`

**Interfaces:**
- No code interfaces.

- [ ] **Step 1: Add `reset-db` to `justfile`**

```make
# Delete local databases/media and rebuild schema v1.
reset-db:
    @pwsh -NoProfile -Command "Remove-Item agentbox.db,e2e.db -ErrorAction SilentlyContinue; Remove-Item -Recurse -Force media,e2e-media -ErrorAction SilentlyContinue"
    uv run alembic -c packages/agentbox-models/alembic.ini upgrade head
```

- [ ] **Step 2: Update `AGENTS.md`**

Add to setup/dev:

- Copy `agentbox.example.toml` to `agentbox.toml` to select Postgres/MySQL/MariaDB.
- `DATABASE_URL`, `DATABASE_*`, and `MEDIA_DIR` override the TOML file.
- `just migrate` uses the same resolver as the app.
- `just reset-db` deletes local DB/media files and applies schema v1.
- Vendor tests use testcontainers and skip without Docker; `AGENTBOX_SKIP_CONTAINERS=1` forces skip.
- Back up the database and media directory together.

- [ ] **Step 3: Update `README.md`**

Replace SQLite-only wording with:

- SQLite default; PostgreSQL 16, MySQL 8, MariaDB 11 supported.
- `agentbox.toml` example and driver mapping.
- Media directory for avatars/attachments/A2A cards; back it up with the DB.
- `just reset-db` for the v1 reset.
- Keep the RoboHash avatar and attachment feature descriptions.

- [ ] **Step 4: Update architecture docs**

- `01-system-overview.md`: SQLite is the default, not the only store; add network DB option.
- `02-tech-stack.md`: asyncpg/aiomysql/aiosqlite, testcontainers, TOML config.
- `03-backend.md`: config resolver, media store, FK/cascade + 409 behavior.
- `05-data-model.md`: rewrite completely for schema v1. Remove JSON/blob encoding rules.
  Document normalized tables, FKs/cascades, media files, and the single initial migration.
- `09-chat-and-streaming.md`: attachments are file-backed; activity is normalized but the
  response shape is unchanged.
- `12-glossary-and-decisions.md`: replace AD-3 “single SQLite database” with “SQLite default,
  network databases supported”.
- `docs/ROADMAP.md`: add schema v1 + vendor portability to the completed/in-progress area that
  matches the repo’s format.

- [ ] **Step 5: Update the Playwright e2e environment**

In `apps/web/playwright.config.ts`, add to the backend server `env`:

```ts
        MEDIA_DIR: "./e2e-media",
```

In `apps/web/e2e/prepare.ts`, remove the e2e media directory:

```ts
await rm(path.resolve(import.meta.dir, "../../../e2e-media"), {
  recursive: true,
  force: true,
});
```

- [ ] **Step 6: Verify docs mention the exact commands**

```powershell
rg -n "reset-db|agentbox.toml|DATABASE_URL|MEDIA_DIR|testcontainers|AGENTBOX_SKIP_CONTAINERS" README.md AGENTS.md docs justfile
```

Expected: all concepts documented.

- [ ] **Step 7: Commit**

```powershell
git add justfile AGENTS.md README.md docs apps/web/playwright.config.ts apps/web/e2e/prepare.ts
git commit -m "docs: document schema v1 and database vendor configuration"
```

---

## Task 10: Final verification

- [ ] **Step 1: Regenerate API artifacts**

```powershell
uv run python apps/web/scripts/gen-openapi.py
cd apps/web
bun run codegen
bun run test
bun run build
```

Expected: PASS.

- [ ] **Step 2: Run backend checks per package**

```powershell
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-api -q
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-providers -q
uv run ruff check packages
uv run ty check packages
```

Expected: PASS. Container tests run when Docker is available; otherwise they skip.

- [ ] **Step 3: Verify no SQLite-only assumptions remain in production code**

```powershell
rg -n "sqlite\+aiosqlite:///\./agentbox\.db|sqlalchemy\.url = sqlite|PRAGMA|SQLiteMessageLogStore" packages/agentbox-api/src packages/agentbox-models/src packages/agentbox-models/alembic.ini
```

Expected: only the default URL constant/resolver, the SQLite FK pragma, and no hard-coded
`alembic.ini` URL.

- [ ] **Step 4: Commit final cleanup**

```powershell
git add packages apps/web docs justfile AGENTS.md README.md
git commit -m "chore: finalize database vendor portability"
```
