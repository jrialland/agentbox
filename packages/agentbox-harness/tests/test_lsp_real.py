import pathlib
import shutil
import subprocess

import pytest

from agentbox_harness.lsp.hooks import make_lsp_hook
from agentbox_harness.lsp.manager import LspManager
from agentbox_harness.tools.registry import ToolHookContext


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


async def _run(project: pathlib.Path, filename: str, content: str):
    manager = LspManager()
    manager.initialize_timeout = 20.0
    manager.diagnostics_timeout = 15.0
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


@pytest.mark.skipif(
    shutil.which("typescript-language-server") is None,
    reason="typescript-language-server not installed",
)
async def test_typescript_language_server(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
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
        tmp_path, "src/main.rs", 'fn main() { let x: i32 = "no"; }\n'
    )
    assert text and "error" in text.lower()
