# AGENTS.md

## Repo shape

- Python uv workspace (`packages/*`) plus a separate Bun/React app (`apps/web`).
- Dependency direction: `agentbox-harness` (pure agent runtime, pydantic-ai, tools, LSP) <- `agentbox-models` (SQLModel tables/repos, Alembic) <- `agentbox-providers` (LLM resolution) <- `agentbox-api` (FastAPI, routers, auth, AG-UI/ACP/A2A).
- Frontend: React 19 + Vite + Mantine + Bulma + RemixIcons, typed `openapi-fetch` client, TanStack Query, Zustand, `mitt` event bus in `src/lib/bus.ts`.
- Backend uses `loguru.logger` throughout; logging setup is in `agentbox_api/logging.py`.
- There is no module-level FastAPI `app`; build it with `create_app(Settings(...))` or run `python -m agentbox_api.dev_server`.

## Domain vocabulary (mandatory)

Keep this distinction explicit in specs, plans, code identifiers, tool names, tests,
and docs. Ambiguous wording here causes real implementation mistakes.

- **Agent** — a configuration record (`Agent` row / `AgentSpec`): model, instructions, tools, modes. An agent is not a live unit and is not "spawned" or "impersonated".
- **Session** (or **agent session**) — a live instance of an agent configuration: project, history, run, status. Sessions are what run, persist, and are monitored.
- **Subagent** — the agent configuration selected by a parent session for a child session. It is a role, not a running thing.
- **Subagent session** — a child session spawned by a parent session (`SessionRow.parent_session_id`) using a subagent configuration.
- Prefer "start a subagent session using an agent configuration" over "spawn an agent" or "run a subagent".
- Canonical tool names: `list_agents`, `start_subagent_session`, `list_subagent_sessions`, `get_subagent_session`, `cancel_subagent_session`, `wait_subagent_session`, `wait_subagent_sessions`.
- Do not introduce `sub_session`, `start_sub_session`, or `delegate_*` vocabulary in new code or docs. Database columns use `subagent_session_*`; the old `sub_session_*` and `agent.sub_agent_ids` columns are removed by migration.
- **Replace, don't layer.** When rewriting or renaming this area, delete the old modules, symbols, tool names, and tests and update every call site. Do not add aliases, re-exports, shims, or dual code paths; leave exactly one delegation mechanism.
- When reviewing or editing this area, correct ambiguous wording instead of propagating it. See `docs/superpowers/specs/2026-11-22-subagent-session-orchestration-design.md`.

## Setup and local dev

- Requires `uv` and `bun`. Run Python commands from the repo root; run frontend commands from `apps/web`.
- `just dev` generates `.env` with a `JWT_SECRET` of at least 32 chars if missing, installs missing dependencies, and seeds `admin` / `admin`. To run the backend directly, set `JWT_SECRET` in `.env` or the environment first.
- Backend: `uv run python -m agentbox_api.dev_server` (port 8000).
- Frontend: `cd apps/web && bun install && bun run dev` (Vite on 5173; `/api` is proxied to 8000 and the prefix is stripped).
- Database defaults to SQLite at `./agentbox.db`. Copy `agentbox.example.toml` to `agentbox.toml` to select PostgreSQL 16, MySQL 8, or MariaDB 11. `DATABASE_URL`, `DATABASE_*`, and `MEDIA_DIR` override the TOML file.
- `dev_server` uses `SQLModel.create_all` plus seeding, so schema changes need an Alembic migration; existing DBs are not auto-altered. Apply with `uv run alembic -c packages/agentbox-models/alembic.ini upgrade head`. `alembic` uses the same TOML/env resolver as the app.
- `just reset-db` deletes local DB/media artifacts and rebuilds schema v1.
- Avatars, attachments, and A2A cards live under the configured media directory; back it up with the database.
- Vendor conformance tests use testcontainers (`postgres:16`, `mysql:8.0`, `mariadb:11`) and skip when Docker is unavailable. Set `AGENTBOX_SKIP_CONTAINERS=1` to force-skip them.
- `just security-report` writes `reports/security/latest.{html,pdf,json}` (gitignored). It runs PySentry, Bandit, Bun audit, and JS-X-Ray and degrades gracefully when a scanner is unavailable.

## Tests and checks

Backend tests, one package per invocation:

```powershell
uv run pytest packages/agentbox-api -q
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-providers -q
```

- Single/focused test: `uv run pytest packages/agentbox-api/tests/test_plan_tools.py -q`.
- Do **not** pass multiple package test directories to one pytest run: duplicate `test_scaffold.py` basenames cause an import-mismatch collection error.
- External integration tests (Ollama, real LSP servers) self-skip when their tools are absent.
- Timeout management is important in tests: every package sets `timeout = 60` (`pytest-timeout`). Do not remove it. When a test hangs, run the focused test with a smaller `--timeout` (e.g. `--timeout=20`) so pytest dumps the stuck stack instead of blocking the suite; fix the root cause rather than raising the limit.

Checks:

```powershell
uv run ruff check --fix packages
uv run ty check packages
```

Frontend:

```powershell
cd apps/web
bun run test      # Vitest; e2e/ is excluded
bun run build     # tsc --noEmit && vite build
bun run e2e       # wipes e2e.db/e2e-skills and starts stub servers + backend + Vite
```

- `bun run e2e` needs ports 5173, 8000, 9000, and 9999 free.
- Use Bun, not npm/pnpm (`bun.lock`). No CI or pre-commit config; run the checks manually.
- Security report tooling: `just test-security-report` runs the `scripts/security-report` Bun tests and TypeScript type-check.

## Generated API artifacts

- `apps/web/openapi.json` and `apps/web/src/api/schema.d.ts` are generated; do not hand-edit the schema. After backend route/schema changes:

```powershell
uv run python apps/web/scripts/gen-openapi.py
cd apps/web
bun run codegen
```

## Repo conventions

- Python: Ruff line length 100, target py311; first-party packages are the `agentbox_*` modules.
- Feature work follows the paired design spec + plan files under `docs/superpowers/specs/` and `docs/superpowers/plans/`. `docs/ROADMAP.md` tracks spec coverage; update it when a feature lands.
- Commit messages follow conventional commits, e.g. `feat(web): ...`, `fix(harness): ...`, `docs(roadmap): ...`.

## Python documentation

- Production Python under `packages/*/src` uses Google-style docstrings for
  modules, public classes, and public functions/methods.
- See `docs/contributing/python-documentation.md`.
- Enforce with `uv run ruff check packages`.
