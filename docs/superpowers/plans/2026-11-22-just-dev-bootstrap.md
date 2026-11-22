# `just dev` First-Run Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `just dev` work from a fresh clone by generating `.env`, installing missing dependencies, and launching both dev servers in parallel with Just's `[parallel]` attribute.

**Architecture:** A new `agentbox_api.dev_prepare` module owns the idempotent bootstrap logic (env file and dependency markers). The justfile calls it before a private `[parallel]` recipe that starts `dev-backend` and `dev-web`. `.env` is gitignored, and README/AGENTS document the first-run behavior.

**Tech Stack:** Python 3.11 standard library, `uv`, `bun`, `just` 1.42+ (`[parallel]` attribute), pytest.

## Global Constraints

- Python 3.11, Ruff line length 100; first-party modules are named `agentbox_*`.
- No new Python or JavaScript dependencies.
- Never print the generated `JWT_SECRET`.
- Leave an existing non-empty `JWT_SECRET` and existing dependency installs untouched.
- `just dev` must work from the repo root on Windows (pwsh via `set windows-shell`) and on Unix-like systems; prep logic is Python, not shell-specific.
- Backend tests are run one package per invocation: `uv run pytest packages/agentbox-api -q`.
- Commit messages follow conventional commits.

---

### Task 1: Bootstrap module and unit tests

**Files:**
- Create: `packages/agentbox-api/src/agentbox_api/dev_prepare.py`
- Test: `packages/agentbox-api/tests/test_dev_prepare.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `dev_prepare.ensure_env(env_path: Path = ENV_PATH) -> bool` - returns `True` when it created or appended a secret.
  - `dev_prepare.ensure_dependencies(root: Path = REPO_ROOT, run=subprocess.run) -> None` - installs only when `.venv` or `apps/web/node_modules` is absent.
  - `dev_prepare.main() -> int` - calls both and returns `0`.
  - Module usable as `python -m agentbox_api.dev_prepare`.

- [ ] **Step 1: Write the failing tests**

Create `packages/agentbox-api/tests/test_dev_prepare.py`:

```python
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbox_api import dev_prepare


def _last_secret(contents: str) -> str:
    values = [
        line.partition("=")[2]
        for line in contents.splitlines()
        if line.partition("=")[0].strip() == "JWT_SECRET"
    ]
    return values[-1] if values else ""


def test_ensure_env_creates_missing_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"

    assert dev_prepare.ensure_env(env) is True

    text = env.read_text(encoding="utf-8")
    assert _last_secret(text)
    assert len(_last_secret(text)) >= 32


def test_ensure_env_leaves_valid_secret_untouched(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    original = f"DATABASE_URL=sqlite+aiosqlite:///:memory:\nJWT_SECRET={'x' * 32}\n"
    env.write_text(original, encoding="utf-8")

    assert dev_prepare.ensure_env(env) is False

    assert env.read_text(encoding="utf-8") == original


def test_ensure_env_appends_when_secret_missing(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "DATABASE_URL=sqlite+aiosqlite:///:memory:\nJWT_SECRET=\n",
        encoding="utf-8",
    )

    assert dev_prepare.ensure_env(env) is True

    text = env.read_text(encoding="utf-8")
    assert "DATABASE_URL=sqlite+aiosqlite:///:memory:" in text
    assert len(_last_secret(text)) >= 32


class FakeRun:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(self, args: list[str], **kwargs: object) -> SimpleNamespace:
        self.calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)


def test_ensure_dependencies_skips_when_present(tmp_path: Path) -> None:
    (tmp_path / ".venv").mkdir()
    (tmp_path / "apps" / "web" / "node_modules").mkdir(parents=True)
    run = FakeRun()

    dev_prepare.ensure_dependencies(tmp_path, run=run)

    assert run.calls == []


def test_ensure_dependencies_installs_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(dev_prepare.shutil, "which", lambda _: "/usr/bin/tool")
    run = FakeRun()

    dev_prepare.ensure_dependencies(tmp_path, run=run)

    assert run.calls == [
        (["uv", "sync"], {"cwd": tmp_path, "check": True}),
        (["bun", "install"], {"cwd": tmp_path / "apps" / "web", "check": True}),
    ]


def test_ensure_dependencies_requires_uv(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(dev_prepare.shutil, "which", lambda _: None)

    with pytest.raises(RuntimeError, match="uv is required"):
        dev_prepare.ensure_dependencies(tmp_path, run=FakeRun())


def test_ensure_dependencies_requires_bun(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".venv").mkdir()
    monkeypatch.setattr(dev_prepare.shutil, "which", lambda _: None)

    with pytest.raises(RuntimeError, match="bun is required"):
        dev_prepare.ensure_dependencies(tmp_path, run=FakeRun())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
uv run pytest packages/agentbox-api/tests/test_dev_prepare.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'agentbox_api.dev_prepare'`.

- [ ] **Step 3: Implement the module**

Create `packages/agentbox-api/src/agentbox_api/dev_prepare.py`:

```python
from __future__ import annotations

import secrets
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
ENV_PATH = REPO_ROOT / ".env"
Run = Callable[..., Any]


def _has_secret(contents: str) -> bool:
    for line in contents.splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == "JWT_SECRET" and value.strip():
            return True
    return False


def ensure_env(env_path: Path = ENV_PATH) -> bool:
    existed = env_path.exists()
    contents = env_path.read_text(encoding="utf-8") if existed else ""
    if _has_secret(contents):
        return False

    secret = secrets.token_urlsafe(48)
    if not existed or not contents:
        env_path.write_text(f"JWT_SECRET={secret}\n", encoding="utf-8")
        print("Creating .env with a generated JWT_SECRET.")
    else:
        separator = "" if contents.endswith("\n") else "\n"
        env_path.write_text(
            f"{contents}{separator}JWT_SECRET={secret}\n",
            encoding="utf-8",
        )
        print("Adding a generated JWT_SECRET to .env.")
    return True


def _require(tool: str, url: str) -> None:
    if shutil.which(tool) is None:
        raise RuntimeError(f"{tool} is required; install it from {url}.")


def ensure_dependencies(root: Path = REPO_ROOT, run: Run = subprocess.run) -> None:
    if not (root / ".venv").exists():
        _require("uv", "https://docs.astral.sh/uv/")
        print("Installing Python dependencies with uv sync.")
        run(["uv", "sync"], cwd=root, check=True)

    web_root = root / "apps" / "web"
    if not (web_root / "node_modules").exists():
        _require("bun", "https://bun.sh/")
        print("Installing frontend dependencies with bun install.")
        run(["bun", "install"], cwd=web_root, check=True)


def main() -> int:
    ensure_env()
    ensure_dependencies()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```powershell
uv run pytest packages/agentbox-api/tests/test_dev_prepare.py -q
```

Expected: `7 passed`.

- [ ] **Step 5: Run Ruff and the type checker**

Run:

```powershell
uv run ruff check packages/agentbox-api/src/agentbox_api/dev_prepare.py packages/agentbox-api/tests/test_dev_prepare.py
uv run ty check packages
```

Expected: both exit successfully with no findings.

- [ ] **Step 6: Commit**

```powershell
git add packages/agentbox-api/src/agentbox_api/dev_prepare.py packages/agentbox-api/tests/test_dev_prepare.py
git commit -m "feat(api): add dev bootstrap helper"
```

---

### Task 2: Wire the justfile and ignore `.env`

**Files:**
- Modify: `justfile:72-82`
- Modify: `.gitignore:3-4`

**Interfaces:**
- Consumes: `agentbox_api.dev_prepare` from Task 1 via `python -m agentbox_api.dev_prepare`.
- Produces: `just dev`, private `just _dev-prepare`, private `[parallel] just _dev-servers`; `dev-backend` and `dev-web` unchanged.

- [ ] **Step 1: Replace the broken `dev` recipe**

In `justfile`, replace the existing backend/web/dev block with:

```just
# Prepare `.env` and any missing dependencies.
_dev-prepare:
    @uv run python -m agentbox_api.dev_prepare

# Start the backend dev server on port 8000.
dev-backend:
    uv run python -m agentbox_api.dev_server

# Start the Vite dev server on port 5173.
dev-web:
    cd apps/web && bun run dev

# Start backend and frontend together.
dev: _dev-prepare
    @just _dev-servers

# Run the backend and frontend dev servers in parallel.
[parallel]
_dev-servers: dev-backend dev-web
```

The old line `just --parallel dev-backend dev-web` must be gone; Just 1.58 rejects
`--parallel`.

- [ ] **Step 2: Ignore the generated env file**

In `.gitignore`, add `.env` directly below `.venv/`:

```gitignore
.venv/
.env
```

- [ ] **Step 3: Verify recipe expansion**

Run:

```powershell
just --dry-run dev
```

Expected: the output includes `uv run python -m agentbox_api.dev_prepare` before
`just _dev-servers`, and does not contain `--parallel`.

- [ ] **Step 4: Smoke-test a fresh first run**

Delete `.env` only if it does not contain a secret you need, then run both servers in the
background and probe them:

```powershell
$proc = Start-Process just -ArgumentList 'dev' -PassThru -NoNewWindow
try {
    Start-Sleep -Seconds 8
    (Invoke-WebRequest http://127.0.0.1:8000/openapi.json -UseBasicParsing).StatusCode
    (Invoke-WebRequest http://localhost:5173 -UseBasicParsing).StatusCode
} finally {
    taskkill /PID $proc.Id /T /F
}
```

Expected: `200` from both URLs. `.env` now exists and contains a `JWT_SECRET` of at least 32
characters; `git status` does not list `.env`.

- [ ] **Step 5: Verify a second run is a no-op**

Run the same smoke test again and capture the preparation output. Expected: no
`Creating .env`, `Adding a generated JWT_SECRET`, or install messages; both probes still
return `200`.

- [ ] **Step 6: Commit**

```powershell
git add justfile .gitignore
git commit -m "fix(dev): bootstrap just dev and run servers in parallel"
```

---

### Task 3: Document the first-run behavior

**Files:**
- Modify: `README.md:135-167`
- Modify: `AGENTS.md` (Setup and local dev section)

**Interfaces:**
- Consumes: the `just dev` behavior from Task 2.
- Produces: documentation that a fresh clone only needs `just dev`.

- [ ] **Step 1: Update README Getting Started**

Replace the install/env/run paragraphs in `README.md` (the text starting at
`Install dependencies from the repo root:` and ending after the separate-server block) with:

````markdown
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
````

Keep the following existing notes (do not delete them) after this block:

- Vite proxies `/api` to port 8000 and strips the prefix.
- The database defaults to `./agentbox.db`; `PORT` overrides the backend port.

- [ ] **Step 2: Update AGENTS.md**

In `AGENTS.md`, replace:

```markdown
- Local backend needs `JWT_SECRET` of at least 32 chars (`.env` or environment). The dev server seeds `admin` / `admin`.
```

with:

```markdown
- `just dev` generates `.env` with a `JWT_SECRET` of at least 32 chars if missing, installs missing dependencies, and seeds `admin` / `admin`. To run the backend directly, set `JWT_SECRET` in `.env` or the environment first.
```

- [ ] **Step 3: Check the documentation diff**

Run:

```powershell
git diff --check
git diff README.md AGENTS.md
```

Expected: no whitespace errors, and the README no longer instructs a fresh clone to create
`.env` manually before running `just dev`.

- [ ] **Step 4: Commit**

```powershell
git add README.md AGENTS.md
git commit -m "docs(dev): document just dev first-run bootstrap"
```

---

## Self-Review

- Spec §1 goals: covered by Tasks 1-2 (fresh clone, idempotency, standalone recipes,
  cross-platform prep).
- Spec §2.1/§2.2: Task 1 creates the module; Task 2 uses `[parallel]` and removes
  `--parallel`.
- Spec §2.3/§2.4: Task 1 implements append-only env handling and marker-based installs.
- Spec §3.3: Task 2 adds `.env` to `.gitignore`.
- Spec §3.4: Task 3 updates README and AGENTS.
- Spec §4: Task 1 tests missing `uv`/`bun`; `CalledProcessError` and `OSError` propagate
  naturally.
- Spec §5: Task 1 unit tests; Task 2 dry-run and smoke checks; Task 3 doc diff check.
- Function names and signatures are consistent across the module, tests, and recipe.
