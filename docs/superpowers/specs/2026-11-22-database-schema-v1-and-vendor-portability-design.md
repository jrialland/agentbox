# Database Schema v1 and Vendor Portability — Design Specification

**Status:** Approved for planning
**Date:** 2026-11-22
**Scope:** `agentbox-models`, `agentbox-api`, `apps/web`, Alembic, tests, docs

## 1. Context

Agentbox currently assumes SQLite everywhere:

- `DATABASE_URL` defaults to `sqlite+aiosqlite:///./agentbox.db`.
- Tests hard-code `sqlite+aiosqlite:///:memory:`.
- `alembic.ini` hard-codes a sync SQLite URL, and `alembic/env.py` creates a sync engine only.
- The schema stores structured application data as JSON (real JSON columns and JSON text) and
  stores uploaded files and avatars as database blobs.

This design makes the persistence layer vendor-neutral and portable across SQLite, PostgreSQL,
MySQL, and MariaDB. Before adding vendor support, it replaces the current schema with a
relational schema v1 that removes JSON-in-column and blob-in-column patterns while preserving
the existing feature set.

There are no production installations. Existing local databases are intentionally discarded;
there is no compatibility layer, data migration, alias, or dual code path.

## 2. Goals

- Support SQLite (default), PostgreSQL 16, MySQL 8, and MariaDB 11 through configuration.
- Add a TOML configuration file (`agentbox.toml`) with environment overrides.
- Replace all structured JSON columns/text with normalized relational tables.
- Move uploaded file bytes (avatars, session attachments, A2A cards) out of the database into a
  configurable media directory, keeping metadata in the database.
- Enforce foreign keys and use database cascades for session-owned data.
- Keep the existing user-facing feature set: avatars, attachments, A2A cards, tool bindings,
  modes, project extra roots, API-key scopes, turn activity/tool details, retry/fork.
- Add a focused testcontainers conformance suite for all four database vendors.
- Provide one clean initial Alembic migration.

## 3. Non-goals

- Migrating existing database contents.
- Supporting SQL Server, Oracle, or other vendors.
- Multi-node deployment, object storage, or a distributed media store.
- Encrypting provider API keys at rest.
- Redesigning the agent/session domain or protocol layers.

## 4. Domain vocabulary

Use the definitions in `AGENTS.md`:

- **Agent** — a configuration record (`Agent` / `AgentSpec`).
- **Session** — a live instance of an agent configuration with project, history, run, and status.
- **Subagent session** — a child session spawned by a parent session.

This spec changes persistence only. Tool names and protocol vocabulary are unchanged.

## 5. Phasing

### Phase 1 — Schema v1 (breaking reset)

- Normalize application-owned structured data.
- Move binary payloads to the media directory.
- Enforce FKs and cascades.
- Delete the existing Alembic version chain and create one initial migration.
- Existing `agentbox.db` and `e2e.db` files are unsupported and must be deleted.

### Phase 2 — Vendor-neutral configuration and runtime

- Add `agentbox.toml` and environment overrides.
- Add a shared database URL resolver used by the app and Alembic.
- Add async drivers for PostgreSQL, MySQL, and MariaDB.
- Make Alembic run migrations through an async engine when needed.

### Phase 3 — Conformance, frontend synchronization, docs

- Add testcontainers fixtures and the conformance suite.
- Regenerate OpenAPI artifacts if the schema changes.
- Update architecture docs, README, AGENTS.md, and ROADMAP.

## 6. Schema v1

### 6.1 Conventions

- All primary keys are application-generated UUID hex strings (`String(32)`).
- Every relationship is a real foreign key.
- Long free-form text uses `sa.Text` explicitly. SQLModel `AutoString` maps no-length strings to
  `VARCHAR(255)` on MySQL/MariaDB, which would silently truncate instructions, messages, and tool
  output.
- Bounded strings use explicit `String(n)` lengths. Unique/indexed text remains within
  MySQL/MariaDB key-length limits.
- Timestamps use SQLModel `UTCDateTime` (timezone-aware UTC).
- Booleans use `Boolean`; counters/durations use `Integer`; file sizes use `BigInteger`.
- Ordered lists have an explicit `position` column.
- No `JSON` columns and no `LargeBinary` columns exist anywhere in schema v1.
- No JSON/array `server_default` expressions. Use Python-side defaults or simple literal SQL
  defaults only.
- Table names stay close to current names to limit churn: `sessionrow`, `turnrow`, `apikey`, etc.
  New tables use descriptive singular names.

### 6.2 Core tables

#### `provider`

| Column | Type | Notes |
|---|---|---|
| `id` | `String(32)` PK | |
| `name` | `String(255)` | |
| `kind` | `String(64)` | Resolver key |
| `base_url` | `String(1024)` nullable | |
| `api_key` | `Text` nullable | Stored plaintext (unchanged behavior) |
| `models_url` | `String(1024)` nullable | |
| `is_builtin` | `Boolean` | |

#### `model`

| Column | Type | Notes |
|---|---|---|
| `id` | `String(32)` PK | |
| `provider_id` | `String(32)` FK → `provider.id` | `ON DELETE RESTRICT` |
| `name` | `String(255)` | |
| `context_window` | `Integer` nullable | |

#### `label`, `model_label_link`

Unchanged shape. `label.name` is unique. Both link columns are FKs to `model.id` and `label.id`
with `ON DELETE CASCADE`.

#### `agent`

| Column | Type | Notes |
|---|---|---|
| `id` | `String(32)` PK | |
| `name` | `String(255)` unique | Route name |
| `description` | `Text` | |
| `instructions` | `Text` | |
| `model_id` | `String(32)` FK → `model.id` | `ON DELETE RESTRICT` |
| `model_label` | `String(255)` nullable | |
| `avatar_file_id` | `String(32)` FK → `media_file.id` nullable | `ON DELETE SET NULL` |
| `created_by` | `String(32)` FK → `user.id` nullable | `ON DELETE SET NULL` |
| `created_at` | `UTCDateTime` | |

Removed: `tool_bindings`, `mode_definitions`, `avatar_url`, `avatar_data`, `avatar_media_type`.

#### `agent_tool_binding`

| Column | Type | Notes |
|---|---|---|
| `id` | `String(32)` PK | |
| `agent_id` | `String(32)` FK → `agent.id` | `ON DELETE CASCADE` |
| `position` | `Integer` | Preserves user order |
| `kind` | `String(16)` | `native` or `mcp` |
| `name` | `String(255)` nullable | Native tool name |
| `server_url` | `Text` nullable | MCP HTTP endpoint |
| `tool_prefix` | `String(255)` nullable | MCP tool prefix |
| `server_id` | `String(255)` nullable | MCP server id |
| `command` | `Text` nullable | MCP stdio command |
| `cwd` | `Text` nullable | MCP stdio working directory |

Unique `(agent_id, position)`.

Child tables (all FK to `agent_tool_binding.id`, `ON DELETE CASCADE`):

- `agent_tool_binding_required_flag`: PK `(binding_id, flag)`; `flag String(255)`.
- `agent_tool_binding_arg`: PK `(binding_id, position)`; `position Integer`, `value Text`.
- `agent_tool_binding_env`: PK `(binding_id, key)`; `key String(255)`, `value Text`.
- `agent_tool_binding_env_passthrough`: PK `(binding_id, position)`; `position Integer`,
  `name String(255)`.

A `native` binding uses `name` and may have required flags. An `mcp` binding uses the MCP columns
and child tables. Repositories reject invalid mixes.

#### `agent_mode`, `agent_mode_flag`

- `agent_mode`: `id String(32)` PK, `agent_id` FK → `agent.id` `ON DELETE CASCADE`,
  `position Integer`, `name String(255)`. Unique `(agent_id, position)`.
- `agent_mode_flag`: PK `(mode_id, name)`; `mode_id` FK → `agent_mode.id` `ON DELETE CASCADE`,
  `name String(64)`, `enabled Boolean`.

#### `agent_card`

| Column | Type | Notes |
|---|---|---|
| `id` | `String(32)` PK | |
| `agent_id` | `String(32)` FK → `agent.id` unique | `ON DELETE CASCADE` |
| `file_id` | `String(32)` FK → `media_file.id` nullable | `ON DELETE SET NULL` |
| `updated_at` | `UTCDateTime` | |

The A2A card is an opaque external protocol document. It is stored as a JSON file under the
media directory, never in a database JSON column.

#### `project`

| Column | Type | Notes |
|---|---|---|
| `id` | `String(32)` PK | |
| `name` | `String(255)` | |
| `path` | `Text` | Absolute project root |
| `owner_id` | `String(32)` FK → `user.id` | `ON DELETE RESTRICT` |
| `created_at` | `UTCDateTime` | |

Removed: `extra_roots`.

#### `project_root`

| Column | Type | Notes |
|---|---|---|
| `id` | `String(32)` PK | |
| `project_id` | `String(32)` FK → `project.id` | `ON DELETE CASCADE` |
| `position` | `Integer` | Preserves order |
| `path` | `Text` | |

Unique `(project_id, position)`.

#### `sessionrow`

| Column | Type | Notes |
|---|---|---|
| `id` | `String(32)` PK | Public session id |
| `project_id` | `String(32)` FK → `project.id` | `ON DELETE RESTRICT` |
| `agent_id` | `String(32)` FK → `agent.id` | `ON DELETE RESTRICT` |
| `title` | `Text` nullable | Auto-generated on first message |
| `parent_session_id` | `String(32)` FK → `sessionrow.id` nullable | `ON DELETE CASCADE` |
| `subagent_session_status` | `String(32)` nullable | |
| `subagent_session_error` | `Text` nullable | |
| `subagent_session_output` | `Text` nullable | |
| `subagent_session_depth` | `Integer` | Default `0` |
| `created_at` | `UTCDateTime` | |

Removed: legacy `head_turn_id`.

Indexes: `project_id`, `agent_id`, `parent_session_id`.

#### `turnrow`

| Column | Type | Notes |
|---|---|---|
| `id` | `String(32)` PK | |
| `session_id` | `String(32)` FK → `sessionrow.id` | `ON DELETE CASCADE` |
| `role` | `String(16)` | `user`, `assistant`, `summary` |
| `content` | `Text` | |
| `parent_id` | `String(32)` FK → `turnrow.id` nullable | `ON DELETE CASCADE` |
| `context_tokens` | `Integer` nullable | |
| `created_at` | `UTCDateTime` | |

Removed: `activity`, `attachments`.

Indexes: `session_id`, `parent_id`.

#### `turn_activity`

One row per turn with activity.

| Column | Type | Notes |
|---|---|---|
| `turn_id` | `String(32)` PK, FK → `turnrow.id` | `ON DELETE CASCADE` |
| `status` | `String(32)` | |
| `reasoning_ms` | `Integer` | Default `0` |
| `reasoning_text` | `Text` | Default `""` |
| `error_code` | `Integer` nullable | |
| `error_message` | `Text` nullable | |

#### `turn_tool_activity`

| Column | Type | Notes |
|---|---|---|
| `id` | `String(32)` PK | |
| `turn_id` | `String(32)` FK → `turnrow.id` | `ON DELETE CASCADE` |
| `position` | `Integer` | Preserves call order |
| `name` | `String(255)` | |
| `status` | `String(32)` | |
| `duration_ms` | `Integer` | |
| `args` | `Text` | Default `""` |
| `result` | `Text` | Default `""` |

Unique `(turn_id, position)`. Tool args/results are truncated by the existing collector before
persistence, preserving current behavior without JSON columns.

#### `media_file`

| Column | Type | Notes |
|---|---|---|
| `id` | `String(32)` PK | |
| `storage_path` | `String(512)` unique | POSIX-style path relative to the media root |
| `media_type` | `String(255)` | |
| `size_bytes` | `BigInteger` | |
| `sha256` | `String(64)` | Lowercase hex |
| `created_at` | `UTCDateTime` | |

#### `session_attachment`

| Column | Type | Notes |
|---|---|---|
| `id` | `String(32)` PK | |
| `session_id` | `String(32)` FK → `sessionrow.id` | `ON DELETE CASCADE` |
| `file_id` | `String(32)` FK → `media_file.id` | `ON DELETE CASCADE` |
| `filename` | `Text` | Original client filename |
| `created_at` | `UTCDateTime` | |

Removed: `data`, `media_type` (now on `media_file`).

#### `turn_attachment`

| Column | Type | Notes |
|---|---|---|
| `turn_id` | `String(32)` FK → `turnrow.id` | `ON DELETE CASCADE` |
| `attachment_id` | `String(32)` FK → `session_attachment.id` | `ON DELETE CASCADE` |
| `position` | `Integer` | Preserves composer order |

Composite PK `(turn_id, attachment_id)`. Unique `(turn_id, position)`.

#### `plan_item`

Unchanged shape except `session_id` is a real FK to `sessionrow.id` with `ON DELETE CASCADE` and
`content` is `Text`.

### 6.3 Auth tables

- `user`: unchanged shape; long fields remain bounded.
- `role`, `permission`: unchanged.
- `role_permission_link`: both columns FKs with `ON DELETE CASCADE`.
- `user_role_link`: both columns FKs with `ON DELETE CASCADE`.
- `apikey`: remove `scopes` text column; `user_id` FK → `user.id` `ON DELETE CASCADE`.
- `apikey_scope`: PK `(api_key_id, scope)`; `api_key_id` FK → `apikey.id` `ON DELETE CASCADE`;
  `scope String(255)`.

### 6.4 Deletion semantics

- Deleting a session cascades to its turns, turn activity/tools, turn links, attachments, plan
  items, and child sessions.
- Deleting an agent cascades to its tool bindings and children, modes/flags, and card row.
  Sessions referencing the agent use `RESTRICT`, so an agent in use cannot be deleted.
- Deleting a model or provider is `RESTRICT` while referenced.
- Deleting a project is `RESTRICT` while sessions exist; the API deletes sessions first.
- Deleting a user cascades to API keys and role links; project ownership and agent creation use
  `RESTRICT`/`SET NULL` as specified above.
- SQLite connections enable `PRAGMA foreign_keys=ON` so SQLite matches PostgreSQL/MySQL/MariaDB.
- API routers catch `IntegrityError` and return `409 Conflict` with a clear message.

### 6.5 Media storage

New `agentbox_api/media.py` owns file storage. The database only stores `media_file` rows.

Layout under the configured media root:

```text
media/
  avatars/{media_id}.png
  attachments/{media_id}{suffix}
  agent-cards/{media_id}.json
```

Rules:

- Storage keys are generated by the application; client filenames never become paths.
- Paths are stored relative to the media root using POSIX separators.
- Writes are atomic: write a temporary file in the same directory, then `os.replace`.
- Every write records `media_type`, `size_bytes`, and `sha256`.
- Upload flow: write file first, then insert DB rows in one transaction; delete the file if the
  transaction fails.
- Delete flow: collect storage paths, delete the owner rows and their `media_file` rows, commit,
  then delete files; missing files are logged and tolerated.
- Avatar GET uses `media_file.sha256` for ETag generation. If a custom avatar file is missing, log
  and fall back to the generated RoboHash avatar.
- A2A card missing file is treated as “no card” (404), matching today’s missing-row behavior.
- Attachment missing file returns 404.
- Session deletion collects attachment file paths before database deletion so cascades cannot hide
  them.
- Agent/card/avatar deletion removes the associated `media_file` row and file.

## 7. Configuration

### 7.1 File discovery

- `AGENTBOX_CONFIG` names an explicit TOML path.
- Otherwise use `./agentbox.toml` if it exists.
- If neither exists, defaults apply.

Add `agentbox.example.toml` to the repository; do not commit a live `agentbox.toml`.

### 7.2 Format

```toml
[database]
vendor = "sqlite"          # sqlite | postgresql | mysql | mariadb
path = "./agentbox.db"     # sqlite only

# Network vendor example:
# vendor = "postgresql"
# host = "localhost"
# port = 5432              # 5432 postgres; 3306 mysql/mariadb
# name = "agentbox"
# user = "agentbox"
# password = "..."         # prefer DATABASE_PASSWORD in the environment
# url = "postgresql+asyncpg://user:pass@host:5432/agentbox"  # full override
# params = { ssl = "require" }

[storage]
media_dir = "./media"
```

### 7.3 Drivers

| Vendor | Async driver | Notes |
|---|---|---|
| `sqlite` | `sqlite+aiosqlite` | Default |
| `postgresql` | `postgresql+asyncpg` | |
| `mysql` | `mysql+aiomysql` | |
| `mariadb` | `mariadb+aiomysql` | Fall back to `mysql+aiomysql` if the dialect is unavailable |

No sync PostgreSQL/MySQL driver is required. Alembic uses the async engine.

### 7.4 URL resolution

- If `database.url` is set, it wins over structured fields (but not over `DATABASE_URL`).
- Otherwise build a URL with `sqlalchemy.URL.create` so usernames, passwords, and params are
  escaped correctly.
- SQLite path defaults to `./agentbox.db`; `:memory:` is allowed.
- `DATABASE_URL` is an escape hatch and wins over TOML.
- Environment overrides: `DATABASE_URL`, `DATABASE_VENDOR`, `DATABASE_HOST`, `DATABASE_PORT`,
  `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_NAME`, `DATABASE_PATH`, `MEDIA_DIR`,
  `AGENTBOX_CONFIG`.
- Precedence: constructor arguments > environment > `.env` > `agentbox.toml` > defaults.

### 7.5 Shared resolver

Create `agentbox_models/config.py`:

- `DatabaseSettings` with `vendor`, `path`, `host`, `port`, `name`, `user`, `password`, `url`,
  `params`.
- `StorageSettings` with `media_dir`.
- `load_config_file()` reads the TOML path.
- `resolve_database_url()` applies env/.env/TOML/default precedence and calls
  `build_database_url()`.
- `normalize_async_url()` converts common sync URLs to their async equivalents.
- `agentbox_api.config.Settings` keeps `database_url: str | None` and fills it from the resolver
  when unset; it adds `media_dir`.
- `alembic/env.py` uses the same resolver. This respects the `agentbox-models` ←
  `agentbox-providers` ← `agentbox-api` dependency direction and avoids duplicated config logic.

`Settings` keeps accepting explicit `database_url=` construction so existing tests and embedded
call sites continue to work.

## 8. Runtime and migrations

### 8.1 Engine factory

`create_engine_and_sessionmaker(database_url, echo=False)`:

- normalizes sync URLs to async equivalents;
- creates an async engine with `pool_pre_ping=True`;
- installs a SQLite connect listener for `PRAGMA foreign_keys=ON`;
- returns `(engine, async_sessionmaker(engine, expire_on_commit=False))`.

`init_db(engine)` remains `SQLModel.metadata.create_all` for tests and the dev server. Real
deployments use Alembic.

### 8.2 Message log

Rename `SQLiteMessageLogStore` to `DatabaseMessageLogStore` and update every import, call site,
and test. No alias remains.

The store:

- writes `TurnRow`;
- writes/updates `TurnActivity` and ordered `TurnToolActivity` rows from `Turn.activity`;
- writes `TurnAttachment` links from `Turn.attachments` for user turns;
- reconstructs `Turn.activity` and `Turn.attachments` on reads via joins.

### 8.3 Alembic

- Delete every file under `packages/agentbox-models/alembic/versions/`.
- Add a single `0001_initial_schema` revision matching schema v1, with a real `downgrade`.
- `alembic.ini` leaves `sqlalchemy.url` empty.
- `alembic/env.py`:
  - uses an explicit `sqlalchemy.url` option when provided (tests/CLI), otherwise the shared
    resolver;
  - detects async dialects with `make_url(...).get_dialect().is_async`;
  - runs online migrations through an async engine and `connection.run_sync`;
  - supports sync URLs (including SQLite file URLs) for tests.
- Delete `packages/agentbox-models/tests/test_subagent_session_migration.py`; replace it with an
  initial-schema test.

### 8.4 Dependencies

`agentbox-models` runtime deps add:

- `asyncpg`
- `aiomysql`
- `python-dotenv` (so Alembic honors `.env`)

Root dev deps add:

- `testcontainers[postgres,mysql,mariadb]`

Existing `aiosqlite` support stays.

## 9. API and frontend behavior

- HTTP shapes stay stable:
  - project `extra_roots` remains `list[str]`, assembled from `project_root`;
  - agent `tool_bindings`/`mode_definitions` remain object lists, assembled from normalized rows;
  - API-key `scopes` remains `list[str]`;
  - turn `attachments` remains a metadata list, assembled through `turn_attachment`;
  - turn `activity` keeps `status`, `reasoning_ms`, `reasoning_text`, `tools` with
    `name`/`status`/`duration_ms`/`args`/`result`, and `error`.
- Avatar, attachment, and A2A-card endpoints keep their paths and response types.
- Ordering is preserved through `position` columns.
- `IntegrityError` from FK enforcement maps to 409.
- Frontend: `ActivityChips` and attachment chips remain; no feature removal. Regenerate
  `apps/web/openapi.json` and `apps/web/src/api/schema.d.ts` and run `bun run codegen`.
- E2E: use a clean `e2e.db` and a temporary media directory.

## 10. Testing

### 10.1 Container fixtures

- Add session-scoped `postgres_url`, `mysql_url`, and `mariadb_url` fixtures in the
  `agentbox-models` and `agentbox-api` test `conftest.py` files. Pytest roots at each package's
  `pyproject.toml`, so a repo-root conftest is not loaded for package-scoped runs.
- Images: `postgres:16`, `mysql:8.0`, `mariadb:11`.
- Build async URLs from container host/port/credentials rather than relying on
  vendor-specific sync drivers.
- Skip when Docker is unavailable; `AGENTBOX_SKIP_CONTAINERS=1` forces skip.
- Containers start once per session; per-test engines are disposed and tables dropped.
- Container-dependent tests use a larger per-test timeout marker while the package-wide
  `timeout = 60` remains unchanged.

### 10.2 Model conformance

`packages/agentbox-models/tests`:

- `test_initial_schema.py`: `alembic upgrade head` on a fresh SQLite file and each container;
  inspect tables, columns, FKs, and indexes; `downgrade base`.
- `test_schema_conformance.py` on all four vendors:
  - long text (>255 chars) and Unicode round-trips (catches MySQL truncation);
  - normalized tool bindings (native flags, MCP args/env/passthrough), modes/flags, project
    roots, API-key scopes;
  - turn activity/tools and turn↔attachment links through `DatabaseMessageLogStore`;
  - FK blocking and cascade deletes.
- `test_dbconfig.py`: TOML parsing, env/.env/TOML precedence, URL escaping, vendor defaults,
  MariaDB fallback; no Docker required.
- `test_migrations_match_metadata.py`: assert the initial migration matches
  `SQLModel.metadata` (no autogenerate diff).

### 10.3 API conformance

`packages/agentbox-api/tests`:

- `test_vendor_api_smoke.py`, parametrized over all four vendors:
  - seed provider/model/user;
  - log in;
  - create an agent with tool bindings, modes, and extra roots;
  - create an API key with scopes;
  - upload an avatar, an attachment, and an A2A card using a `tmp_path` media directory;
  - read them back and assert bytes/metadata;
  - delete and assert files and rows are removed.
- `test_media_store.py`: atomic write/read/delete, SHA-256, filename sanitization, path traversal
  rejection, missing-file tolerance.

### 10.4 Existing test updates

Enabling FKs means existing tests that insert orphan rows must seed referenced rows. In
particular:

- attachment tests must create a real `sessionrow` before uploading;
- table/CRUD tests that insert an `agent` with `model_id` must seed the provider and model;
- tests that insert turns must seed the session and parent chain where applicable.

These are fixture updates, not behavior changes.

### 10.5 Checks

Run the normal checks from `AGENTS.md`:

```powershell
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-api -q
uv run ruff check --fix packages
uv run ty check packages
cd apps/web
bun run test
bun run build
```

## 11. Migration reset and developer workflow

- Delete old local DB files (`agentbox.db`, `e2e.db`) before running v1.
- Add `just reset-db`:
  - removes `agentbox.db` and `e2e.db`,
  - removes the configured dev media directory,
  - runs `alembic upgrade head`.
- `.gitignore` includes the default media directory.
- Document that a v1 installation needs both the database and the media directory backed up.

## 12. Documentation updates

- `README.md`: supported vendors, `agentbox.toml`, media directory, reset instructions.
- `docs/architecture/01-system-overview.md`: SQLite is the default, not the only store.
- `docs/architecture/02-tech-stack.md`: drivers, testcontainers, config file.
- `docs/architecture/03-backend.md`: config resolution, media store, deletion behavior.
- `docs/architecture/05-data-model.md`: full rewrite for schema v1.
- `docs/architecture/09-chat-and-streaming.md`: file-backed attachments and normalized activity.
- `docs/architecture/12-glossary-and-decisions.md`: replace the “single SQLite database” decision.
- `AGENTS.md`: configuration, vendor tests, testcontainers opt-out.
- `docs/ROADMAP.md`: record schema v1 and vendor portability.

## 13. Feature-preservation analysis

### Preserved without change

- Avatar upload/reset and RoboHash defaults.
- Session attachment upload/download.
- A2A custom card editing/serving.
- Agent tool bindings (native/MCP, args/env/passthrough), modes/flags, project roots, API-key
  scopes.
- Turn attachment chips, retry, and fork.
- Full turn activity details (reasoning text, tool args, tool results), now in `Text` columns.
- SQLite as the default database.

### Operational changes, not feature removals

- Media must be backed up with the database.
- File and DB writes are not a single transaction; the write order and cleanup rules above
  mitigate this.
- A lost media file degrades gracefully (default avatar, 404 card/attachment) instead of leaving
  a usable DB row.
- Adding new tool-binding/mode fields requires an Alembic migration instead of accepting
  arbitrary JSON.

### Intentionally lost

- Existing local database contents, because there is no compatibility migration.

## 14. Alternatives considered

1. **Keep JSON/blob columns and add dialect variants.** Smaller diff, but keeps the schema
   antipatterns and makes the data model vendor-specific through JSON/BLOB behavior. Rejected.
2. **Put configuration only in the API layer.** Would force Alembic to duplicate TOML parsing or
   require exported environment variables. Rejected.
3. **Use sync database drivers for Alembic.** Adds duplicate dependencies and splits the URL
   handling. Rejected in favor of async Alembic.
4. **Keep tool activity as summary only.** Rejected because it removes working history/UI and
   weakens audit data; normalized `Text` columns preserve behavior.

## 15. Risks

- FK enforcement may expose delete-order bugs; fix them rather than weakening constraints.
- MySQL/MariaDB key-length and row-size limits require explicit lengths and conformance tests.
- Asyncpg/aiomysql and MariaDB dialect registration must be verified during implementation.
- Container tests are slower and Docker-dependent; they are skippable.
- `agentbox.toml` parsing must not change default behavior when no file exists.
- The initial migration and metadata must stay in sync; a metadata-diff test guards this.

## 16. Acceptance criteria

- No `JSON` or `LargeBinary` columns remain in `SQLModel.metadata`.
- No binary payloads are written to the database.
- A fresh database on SQLite, PostgreSQL 16, MySQL 8, and MariaDB 11 can be created with
  `alembic upgrade head` and used for the full core CRUD/API flows.
- `agentbox.toml` selects each vendor; environment variables and `DATABASE_URL` override it.
- Existing features listed in section 13 pass on every vendor in the conformance suite.
- SQLite and the other vendors enforce the same FK/cascade behavior.
- All backend checks and frontend tests/build pass.
- Docs and OpenAPI artifacts reflect the new configuration, schema, and behavior.
