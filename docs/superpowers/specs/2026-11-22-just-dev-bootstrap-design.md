# `just dev` First-Run Bootstrap - Design Specification

## 1. Context and Scope

`just dev` is documented in `README.md` and `AGENTS.md` as the way to start the backend and
frontend together, but it does not work on a fresh clone:

- `justfile` calls `just --parallel dev-backend dev-web`. The `--parallel` command-line flag was
  removed by Just; 1.58.0 rejects it with `error: unexpected argument '--parallel' found`.
- The backend requires `JWT_SECRET` through `Settings`, and no `.env` exists on a fresh clone, so
  `just dev-backend` fails with `jwt_secret Field required`.
- `.env` is not in `.gitignore`, which becomes a secret-leak risk once a generated secret is
  written there.

This sub-project makes `just dev` the single first-run command: it prepares `.env` and missing
dependencies, then starts both servers in parallel.

### 1.1 Goals

- `just dev` works from a fresh clone after `uv` and `bun` are installed.
- Existing `.env` values and installed dependencies are left untouched.
- `just dev-backend`, `just dev-web`, and `just setup` remain usable independently.
- The recipe works on Windows (the repo's current shell setup) and on Unix-like systems.

### 1.2 Boundaries (out of scope)

- Installing `uv`, `bun`, or `just` themselves.
- Running Alembic migrations automatically. The dev server still uses `create_all` plus the
  admin seed; existing databases keep the documented manual migration step.
- Changing backend settings, ports, or the Vite proxy.
- Adding `.env.example` or a configuration wizard.

## 2. Decisions and Rationale

### 2.1 Prep logic in a testable Python module (Approach A)

Three approaches were considered:

- **A. Justfile fix plus a Python prep module (chosen).** `dev` calls
  `uv run python -m agentbox_api.dev_prepare`; a `[parallel]` sub-recipe starts the servers.
  One place for bootstrap logic, importable by package tests, no shell-specific conditionals.
- **B. Pure justfile with `[windows]`/`[unix]` variants.** No extra module, but duplicates
  file-existence and env handling per platform, and inline quoting is fragile.
- **C. Bootstrap inside `dev_server.py`.** Backend would create `.env` before loading `Settings`,
  but the frontend dependency check would still live in the justfile and application code would
  carry local-dev ergonomics.

A keeps the justfile declarative and places logic where it can be unit-tested under the existing
`agentbox-api` test suite. It lives in `packages/agentbox-api/src/agentbox_api/dev_prepare.py`,
next to `dev_server.py`, rather than a new root `scripts/` directory.

### 2.2 Use Just's `[parallel]` attribute

Just 1.42+ replaced command-line parallelism with the `[parallel]` recipe attribute, which runs a
recipe's dependencies concurrently. The `dev` recipe calls a private recipe:

```just
dev: _dev-prepare
    @just _dev-servers

[parallel]
_dev-servers: dev-backend dev-web
```

This avoids the removed flag and keeps preparation ordered before either server starts. No
`--jobs` limit is needed for two recipes.

### 2.3 Append-only `.env` handling

A missing `.env` is created with a generated `JWT_SECRET`. If `.env` exists with a non-empty
`JWT_SECRET`, it is not modified. If the key is missing or empty, a generated line is appended;
existing lines are never rewritten or reordered. Generated secrets use
`secrets.token_urlsafe(48)` (well above the 32-character minimum) and are never printed.

### 2.4 Install dependencies only when their markers are absent

The prep module runs `uv sync` only when `.venv/` is missing and `bun install` only when
`apps/web/node_modules/` is missing. This keeps normal startup fast and makes first-run behavior
automatic. Note that the `uv run` invocation itself creates/syncs the Python environment, so the
`.venv` check is a guard for direct module invocation and for clarity. Missing `uv` or `bun`
executables produce a clear error instead of a partial install.

## 3. Detailed Design

### 3.1 `just dev` flow

1. `just dev` runs the private `_dev-prepare` recipe.
2. `_dev-prepare` runs `uv run python -m agentbox_api.dev_prepare`.
3. The module ensures `.env` and missing dependencies, printing one short line per action.
4. `just dev` runs `just _dev-servers`.
5. `_dev-servers` starts `dev-backend` (port 8000) and `dev-web` (port 5173) in parallel.

If preparation fails, neither server starts and the process exits non-zero.

### 3.2 `agentbox_api.dev_prepare`

The module uses only the standard library. Functions take explicit paths and an injectable runner
so tests do not invoke real installers:

- `ensure_env(env_path: Path) -> bool`: create or append as described in §2.3; return whether a
  change was made.
- `ensure_dependencies(root: Path, run=subprocess.run) -> None`: check `.venv` and
  `apps/web/node_modules`; run `uv sync` and/or `bun install` as needed. Check executables with
  `shutil.which` and raise a `RuntimeError` naming the tool and install URL when absent.
- `main() -> int`: derive the repo root from `Path(__file__).resolve().parents[4]` (the module is
  four levels below the repo root: `packages/agentbox-api/src/agentbox_api`), call both functions,
  and return `0`. The `-m` entry point raises `SystemExit(main())`.

Printed messages:

- `Creating .env with a generated JWT_SECRET.`
- `Adding a generated JWT_SECRET to .env.`
- `Installing Python dependencies with uv sync.`
- `Installing frontend dependencies with bun install.`

### 3.3 Git hygiene

Add `.env` to `.gitignore` so the generated secret cannot be committed. No other ignore rules
change; `.env.example` is not introduced.

### 3.4 Documentation

- `README.md` Getting Started: `just dev` is the primary first-run command and creates `.env` /
  installs missing dependencies. Keep the manual install, `.env`, and separate-server commands
  for developers who prefer them.
- `AGENTS.md` Setup and local dev: note that `just dev` generates `JWT_SECRET` and installs
  missing dependencies, while the manual backend/frontend commands remain authoritative for
  focused work.
- `docs/architecture/02-tech-stack.md` mentions `just dev`; no change is required beyond its
  existing one-line description.

## 4. Error Handling

- Missing `bun`: exit 1 with `bun is required for frontend development; install it from
  https://bun.sh/`.
- Missing `uv`: exit 1 with `uv is required; install it from https://docs.astral.sh/uv/`.
- Installer failure: propagate `subprocess.CalledProcessError`, which exits non-zero and shows
  the failing command output.
- `.env` write failure (permissions, read-only checkout): propagate `OSError` with the path in
  the error message.
- Existing malformed `.env` with duplicate/empty keys is handled by appending only when no
  non-empty `JWT_SECRET` exists; no parser or rewrite is attempted.

## 5. Testing and Verification

### 5.1 Unit tests

`packages/agentbox-api/tests/test_dev_prepare.py` covers:

1. Missing `.env` is created with a non-empty `JWT_SECRET` of at least 32 characters.
2. Existing `.env` with unrelated variables and a valid secret is unchanged.
3. Existing `.env` without a secret gets one appended; unrelated lines and an empty
   `JWT_SECRET=` line are preserved.
4. Dependency checks skip commands when `.venv` and `apps/web/node_modules` exist.
5. Missing markers invoke `uv sync` at the repo root and `bun install` in `apps/web`, using an
   injected fake runner.
6. A missing executable raises a clear `RuntimeError`.

Run with:

```powershell
uv run pytest packages/agentbox-api/tests/test_dev_prepare.py -q
```

### 5.2 Recipe verification

1. `just --dry-run dev` shows preparation before `_dev-servers`, and no `--parallel` flag.
2. `just dev` on a checkout without `.env` creates `.env`, starts both servers, and
   `http://127.0.0.1:8000` plus `http://localhost:5173` respond.
3. Stop the process with Ctrl+C; both servers exit.
4. Re-run `just dev`: `.env` is not modified and dependencies are not reinstalled.

## 6. Files Changed

- `justfile` - fix `dev`, add `_dev-prepare` and `[parallel] _dev-servers`.
- `packages/agentbox-api/src/agentbox_api/dev_prepare.py` - new bootstrap module.
- `packages/agentbox-api/tests/test_dev_prepare.py` - new unit tests.
- `.gitignore` - ignore `.env`.
- `README.md`, `AGENTS.md` - document the first-run behavior.
- `docs/superpowers/plans/2026-11-22-just-dev-bootstrap.md` - implementation plan.
