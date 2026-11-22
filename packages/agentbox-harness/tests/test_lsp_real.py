import pathlib
import shutil
import subprocess
import sys
from dataclasses import replace

import pytest

from agentbox_harness.lsp.hooks import make_lsp_hook
from agentbox_harness.lsp.manager import LspManager
from agentbox_harness.lsp.stacks import DEFAULT_LSP_SERVERS
from agentbox_harness.tools.registry import ToolHookContext

pytestmark = pytest.mark.timeout(300)

PROVISION_TIMEOUT = 60.0


def _manager(settle: float | None = None) -> LspManager:
    manager = LspManager()
    manager.initialize_timeout = PROVISION_TIMEOUT
    manager.diagnostics_timeout = PROVISION_TIMEOUT
    if settle is not None:
        manager.stacks = [
            replace(stack, settle=settle) for stack in DEFAULT_LSP_SERVERS
        ]
    return manager


def _available(tool: str) -> bool:
    path = shutil.which(tool)
    if not path:
        return False
    try:
        return (
            subprocess.run([path, "--version"], capture_output=True, timeout=5)
            .returncode
            == 0
        )
    except Exception:
        return False


def _install_typescript(project: pathlib.Path) -> None:
    npm = shutil.which("npm")
    if npm is None:
        pytest.skip("npm not installed")
    command = ["cmd", "/c", npm] if sys.platform == "win32" else [npm]
    try:
        result = subprocess.run(
            [*command, "install", "--no-save", "--no-package-lock", "typescript@5.9.3"],
            cwd=project,
            capture_output=True,
            timeout=180,
        )
    except Exception as exc:
        pytest.skip(f"npm install typescript failed: {exc}")
    if result.returncode != 0:
        pytest.skip(f"npm install typescript failed: {result.stderr[-200:]!r}")


async def _run(
    project: pathlib.Path,
    filename: str,
    content: str,
    *,
    settle: float | None = None,
):
    manager = _manager(settle)
    path = project / filename
    path.write_text(content, encoding="utf-8")
    hook = make_lsp_hook(manager, "real", str(project))
    ctx = ToolHookContext(
        tool_name="write_file", args={"path": str(path)}, root=project, result="ok"
    )
    try:
        return await hook(ctx)
    finally:
        await manager.shutdown()


@pytest.mark.skipif(shutil.which("uvx") is None, reason="uvx not installed")
async def test_python_ty(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'x'\nversion = '0.1.0'\n", encoding="utf-8"
    )
    text = await _run(tmp_path, "a.py", 'x: int = "not an int"\n')
    assert text and "error" in text.lower()


@pytest.mark.skipif(shutil.which("npx") is None, reason="npx not installed")
async def test_typescript_language_server(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions": {"strict": true}}', encoding="utf-8"
    )
    _install_typescript(tmp_path)
    text = await _run(tmp_path, "a.ts", 'const x: number = "no";\n')
    assert text and "error" in text.lower()


@pytest.mark.skipif(
    not _available("rust-analyzer") or shutil.which("cargo") is None,
    reason="rust-analyzer/cargo not installed",
)
async def test_rust_analyzer(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        "[package]\nname = 'x'\nversion = '0.1.0'\nedition = '2021'\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    text = await _run(
        tmp_path,
        "src/main.rs",
        'fn main() { let x: i32 = "no"; }\n',
        settle=PROVISION_TIMEOUT,
    )
    assert text and "error" in text.lower()


@pytest.mark.skipif(
    not _available("rust-analyzer") or shutil.which("cargo") is None,
    reason="rust-analyzer/cargo not installed",
)
async def test_rust_analyzer_clean_write_returns_no_diagnostics(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        "[package]\nname = 'x'\nversion = '0.1.0'\nedition = '2021'\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    text = await _run(
        tmp_path,
        "src/main.rs",
        'fn main() { let x: i32 = 1; println!("{}", x); }\n',
    )
    assert text is None
