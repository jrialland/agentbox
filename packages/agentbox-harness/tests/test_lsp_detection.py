from agentbox_harness.lsp.detect import detect_stacks
from agentbox_harness.lsp.stacks import DEFAULT_LSP_SERVERS, language_for


def test_detects_multiple_stacks_in_subdirs(tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "main.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    names = [stack.name for stack in detect_stacks(str(tmp_path))]
    assert "python" in names
    assert "typescript" in names


def test_prunes_vendor_dirs(tmp_path):
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "package.json").write_text("{}", encoding="utf-8")
    assert detect_stacks(str(tmp_path)) == []


def test_no_stack_when_no_markers(tmp_path):
    assert detect_stacks(str(tmp_path)) == []


def test_language_for_extension():
    python = DEFAULT_LSP_SERVERS[0]
    assert language_for(python, "main.py") == "python"
    assert language_for(python, "main.ts") is None


def test_rust_default_uses_server_status_quiescence():
    rust = next(stack for stack in DEFAULT_LSP_SERVERS if stack.name == "rust")
    assert rust.quiescence == "server_status"
    assert rust.pull is False
    assert rust.save is True
    assert rust.settle == 15.0


def test_other_default_stacks_have_no_quiescence():
    others = [stack for stack in DEFAULT_LSP_SERVERS if stack.name != "rust"]
    assert all(stack.quiescence is None for stack in others)
