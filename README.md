# Agentbox

A self-hosted agentic platform: a Pydantic AI harness, a FastAPI backend, and a React
"command-center" web UI. Agentbox is built around open agent protocols and exists to be
hackable, observable, and pleasant to operate locally.

## Intent

Agentbox turns a local project folder into a workspace for tool-using LLM agents. An agent is
a system prompt plus a set of tools, a model, and optional modes; a session binds that agent to
one project folder and keeps its history in a relational database (SQLite by default; PostgreSQL,
MySQL, or MariaDB through configuration). Sessions can start subagent sessions using
any agent configuration, then monitor, wait for, or cancel them.

The guiding constraints are:

- **Protocol compliance over homegrown plumbing.** The platform interoperates through AG-UI
  (web streaming), ACP (IDE over stdio), A2A (agent-to-agent with agent cards), and MCP
  (external tools/resources). Where a standard exists, use the official SDK or the pydantic-ai
  adapter rather than inventing a wire format.
- **Local-first and self-hosted.** One SQLite database by default, one backend, one web app.
  PostgreSQL, MySQL, and MariaDB are supported through `agentbox.toml`. No hosted control plane
  is required.
- **Ambition in the UI.** The frontend is a deliberately composed product, not a form over an
  API: a design system, a real shell, precise components, and a typed event bus.
- **Async where possible.** Backend work runs on async FastAPI, async SQLModel/SQLAlchemy, and
  async pydantic-ai.

## Features

### Agents and tools

- Agent definitions with name, description, system prompt, tool selection, model, and modes.
- Default RoboHash (set 1) avatars, with optional uploaded photos.
- A reference filesystem toolset: read, write, tree, search, file info, media reads, guarded
  delete, plus bounded `grep`.
- Terminal management scoped to allowed project roots.
- Keyless web search (ddgs/SearXNG) and URL fetch with extraction.
- Skills discovery and explicit activation, with `/` autocomplete in the composer.
- `AGENTS.md` project instructions and Jinja-based prompt templating.
- Automatic LSP diagnostics across stacks, including Rust server-status quiescence.
- Session plan tools (TODO-style), automatic context compaction, and background subagent
  sessions with live output, wait all/any, and recursive cancellation.

### Chat and sessions

- AG-UI streaming consumed by the web app via `@ag-ui/client`.
- Ordered live segments, visible reasoning and tool traces, Markdown, syntax highlighting, and
  Mermaid diagrams with pan/zoom and source copy.
- Attachments, drag-and-drop, speech-to-text, and `@` file autocomplete relative to the project
  root.
- Session history, edit/fork with a visible fork banner, per-turn retry, and a stop control.
- Ask/Agent mode switching, with modes defined in the agent configuration.

### Providers and models

- OpenAI legacy completions, OpenAI Responses, Anthropic Messages, and generic
  base-URL/API-key/API-type providers.
- Known providers such as Moonshot and DeepSeek with pre-filled URLs and environment-variable
  keys.
- Model discovery from provider endpoints, persisted model lists, and label-based routing.

### Platform

- Projects and a projects → sessions tree.
- MCP Apps rendered in right-side tabs without interrupting the conversation.
- RBAC (users → roles → permissions), admin CRUD, and scoped personal API keys with optional
  expiry.
- ACP adapter (`agentbox-acp`, also `python -m agentbox_api.acp_server`) and A2A endpoints at
  `/a2a/{agent}` for agents with an agent card.
- Loguru logging with console/file sinks, rotation, and retention.

## Architecture

Packages depend downward; the web app talks to the API over HTTP and AG-UI:

```
apps/web  (React 19 + Vite, separate Bun project)
    │  HTTP + AG-UI
    ▼
agentbox-api        FastAPI app factory, routers, auth/RBAC, AG-UI/ACP/A2A, MCP relay
    │
agentbox-providers  provider/model resolution
    │
agentbox-models     SQLModel tables/repositories, Alembic migrations
    │
agentbox-harness    pure agent runtime: pydantic-ai agent factory, tools, LSP, compaction
```

- `packages/agentbox-harness` — agent runtime and tools. It knows nothing about HTTP or the
  database.
- `packages/agentbox-models` — persistence models and repositories.
- `packages/agentbox-providers` — resolves provider configuration into pydantic-ai models.
- `packages/agentbox-api` — FastAPI application, routers, authentication, protocol adapters.
- `apps/web` — React frontend, a standalone Bun project rather than a uv workspace member.

There is intentionally no module-level FastAPI `app`. Build one with `create_app(Settings(...))`
or run the development server.

## Visual style

The UI direction is a **technical command center with hacker/computer-culture pop**: pixel
display type, a phosphor palette, restrained CRT accents, and a dense operator-console layout.

- Dark-first, system-aware, with a visible light/dark toggle.
- Phosphor green, amber, cyan, and magenta accents on a near-black canvas.
- Silkscreen for display/nav labels, Inter for UI copy, JetBrains Mono for code and metadata.
- RemixIcon line icons through a shared wrapper; icon-only actions require labels and tooltips.
- A 3-pane desktop shell (icon rail, project panel, workspace); segmented nav and a project
  sheet on mobile.
- Mantine-first components, CSS-variable tokens, and Storybook as the review surface.

The full token, typography, and component rules live in
[`docs/superpowers/specs/2026-11-20-ux-1-design-system-design.md`](docs/superpowers/specs/2026-11-20-ux-1-design-system-design.md).

## Engineering conventions

- Python 3.11, Ruff at line length 100, first-party modules named `agentbox_*`.
- Async throughout; `loguru.logger` for backend logs; SQLModel/Alembic for schema changes.
- Tests run one package per invocation (duplicate test basenames break collection); every
  package sets a 60-second `pytest-timeout`.
- Frontend: React 19, Vite, Mantine, TanStack Query, Zustand, a typed `openapi-fetch` client,
  and a `mitt` event bus in `src/lib/bus.ts`. Use Bun, not npm or pnpm.
- Generated OpenAPI artifacts (`apps/web/openapi.json`, `apps/web/src/api/schema.d.ts`) are
  never hand-edited.
- Feature work follows a paired design spec and plan under `docs/superpowers/`; update
  `docs/ROADMAP.md` when a feature lands.
- Commit messages use conventional commits, e.g. `feat(web): ...`, `fix(harness): ...`.

See [`AGENTS.md`](AGENTS.md) for the same rules in agent-oriented form.

## Getting started

Prerequisites: [uv](https://docs.astral.sh/uv/), [Bun](https://bun.sh/), and optionally
[just](https://github.com/casey/just).

From the repo root, start everything with:

```powershell
just dev
```

On the first run, `just dev` creates `.env` with a generated `JWT_SECRET` of at least 32
characters, installs Python or frontend dependencies if they are missing, then starts the
backend on `http://127.0.0.1:8000` and Vite on `http://localhost:5173`. The development
server seeds an `admin` / `admin` user.

To install dependencies without starting the servers, run `just setup`. To run the servers
separately:

```powershell
uv run python -m agentbox_api.dev_server   # http://127.0.0.1:8000
cd apps/web; bun run dev                    # http://localhost:5173
```

For an existing database, apply migrations instead of relying on the dev server's
`create_all`:

```powershell
uv run alembic -c packages/agentbox-models/alembic.ini upgrade head
```

Vite proxies `/api` to port 8000 and strips the prefix. The database defaults to
`./agentbox.db`; `PORT` overrides the backend port.

Copy `agentbox.example.toml` to `agentbox.toml` to select PostgreSQL 16, MySQL 8, or MariaDB 11.
The driver mapping is `postgresql+asyncpg`, `mysql+aiomysql`, and `mariadb+aiomysql` (falling back
to `mysql+aiomysql` when the MariaDB dialect is unavailable). `DATABASE_URL`, `DATABASE_*`, and
`MEDIA_DIR` override the TOML file. Avatars, attachments, and A2A cards are stored under the
configured media directory, so back up the database and media directory together. To discard a
pre-v1 local database and rebuild schema v1, run `just reset-db`.

## Repository layout

```
packages/
  agentbox-harness/    agent runtime, tools, LSP, compaction
  agentbox-models/     SQLModel tables, repositories, Alembic
  agentbox-providers/  LLM provider/model resolution
  agentbox-api/        FastAPI app, routers, auth, protocol adapters
apps/web/              React + Vite frontend (Bun project)
docs/                  initial spec, roadmap, UX reviews, specs, plans
justfile               common tasks (setup, dev, check, verify)
AGENTS.md              contributor/agent conventions
```

## Checks

Backend, one package per invocation:

```powershell
uv run ruff check --fix packages
uv run ty check packages
uv run pytest packages/agentbox-api -q
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-providers -q
```

Frontend, from `apps/web`:

```powershell
bun run test      # Vitest, e2e/ excluded
bun run build     # tsc --noEmit && vite build
bun run e2e       # Playwright; ports 5173, 8000, 9000, 9999 must be free
```

Regenerate API artifacts after backend route or schema changes:

```powershell
uv run python apps/web/scripts/gen-openapi.py
cd apps/web
bun run codegen
```

`just check` runs lint and all tests; `just verify` formats, lints, tests, and builds.

## Documentation

- [`docs/initial_spec.md`](docs/initial_spec.md) — the original product specification.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — requirement coverage and sub-project history.
- [`docs/superpowers/specs/`](docs/superpowers/specs/) and
  [`docs/superpowers/plans/`](docs/superpowers/plans/) — per-feature designs and plans.
- [`docs/reviews/`](docs/reviews/) — UX review reports and screenshots.

## Credits

Default agent avatars are generated with [RoboHash](https://robohash.org) (set 1).
RoboHash code is MIT-licensed (Copyright (c) 2011, e1ven); set 1 artwork is by
Zikri Kader, CC-BY-3.0/CC-BY-4.0. "Robots lovingly delivered by Robohash.org."
See [`NOTICE`](NOTICE) for the packaged attribution.
