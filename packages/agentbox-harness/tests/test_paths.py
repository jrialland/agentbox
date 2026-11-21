import pytest

from agentbox_harness.tools.paths import resolve_project_path


def test_resolve_project_path_defaults_to_root(tmp_path):
    assert resolve_project_path("", str(tmp_path)) == tmp_path.resolve()


def test_resolve_project_path_relative_to_root(tmp_path):
    (tmp_path / "sub").mkdir()
    assert resolve_project_path("sub", str(tmp_path)) == (tmp_path / "sub").resolve()


def test_resolve_project_path_allows_extra_root(tmp_path):
    root = tmp_path / "root"
    extra = tmp_path / "extra"
    root.mkdir()
    extra.mkdir()
    assert resolve_project_path(str(extra), str(root), [str(extra)]) == extra.resolve()


def test_resolve_project_path_rejects_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ValueError, match="escapes allowed roots"):
        resolve_project_path("../outside", str(root))
