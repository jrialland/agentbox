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
