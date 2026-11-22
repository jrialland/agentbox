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
