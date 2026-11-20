# AGENTS.md

## Repo shape

- Python uv workspace (`packages/*`) plus a separate Bun/React app (`apps/web`).
- Dependency direction: `agentbox-harness` (pure agent runtime, pydantic-ai, tools, LSP) <- `agentbox-models` (SQLModel tables/repos, Alembic) <- `agentbox-providers` (LLM resolution) <- `agentbox-api` (FastAPI, routers, auth, AG-UI/ACP/A2A).
- Frontend: React 19 + Vite + Mantine + Bulma + RemixIcons, typed `openapi-fetch` client, TanStack Query, Zustand, `mitt` event bus in `src/lib/bus.ts`.
- Backend uses `loguru.logger` throughout; logging setup is in `agentbox_api/logging.py`.
- There is no module-level FastAPI `app`; build it with `create_app(Settings(...))` or run `python -m agentbox_api.dev_server`.

## Setup and local dev

- Requires `uv` and `bun`. Run Python commands from the repo root; run frontend commands from `apps/web`.
- Local backend needs `JWT_SECRET` of at least 32 chars (`.env` or environment). The dev server seeds `admin` / `admin`.
- Backend: `uv run python -m agentbox_api.dev_server` (port 8000).
- Frontend: `cd apps/web && bun install && bun run dev` (Vite on 5173; `/api` is proxied to 8000 and the prefix is stripped).
- Database defaults to `./agentbox.db`. `dev_server` uses `SQLModel.create_all` plus seeding, so schema changes need an Alembic migration; existing DBs are not auto-altered. Apply with `uv run alembic -c packages/agentbox-models/alembic.ini upgrade head`.

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
