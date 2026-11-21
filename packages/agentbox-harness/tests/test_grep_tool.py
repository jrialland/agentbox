import pathlib
from dataclasses import replace

import pytest

from agentbox_harness.tools.grep import GrepOptions, run_grep


def options(root: pathlib.Path, pattern: str, **kwargs) -> GrepOptions:
    return replace(
        GrepOptions(pattern=pattern, root=root, project_root=root), **kwargs
    )


def test_finds_matches_with_path_line_and_column(tmp_path: pathlib.Path):
    (tmp_path / "a.txt").write_text("first\nneedle here\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("needle again\n", encoding="utf-8")

    out = run_grep(options(tmp_path, "needle"))

    assert "a.txt:2:1:needle here" in out
    assert "sub/b.txt:1:1:needle again" in out
    assert out.count("needle") == 2


def test_regex_and_fixed_string_modes(tmp_path: pathlib.Path):
    (tmp_path / "a.txt").write_text("foo42 foo_bar\n", encoding="utf-8")

    assert "foo42" in run_grep(options(tmp_path, r"foo\d+"))
    assert "foo42" not in run_grep(options(tmp_path, r"foo\d+", fixed_strings=True))
    assert "foo_bar" in run_grep(options(tmp_path, "foo_bar", fixed_strings=True))


def test_ignore_case_and_invalid_regex(tmp_path: pathlib.Path):
    (tmp_path / "a.txt").write_text("Needle\n", encoding="utf-8")
    assert "Needle" not in run_grep(options(tmp_path, "needle"))
    assert "Needle" in run_grep(options(tmp_path, "needle", ignore_case=True))
    with pytest.raises(ValueError, match="Invalid regex"):
        run_grep(options(tmp_path, "["))


def test_include_exclude_and_default_excludes(tmp_path: pathlib.Path):
    (tmp_path / "keep.py").write_text("hit\n", encoding="utf-8")
    (tmp_path / "skip.md").write_text("hit\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("hit\n", encoding="utf-8")

    out = run_grep(options(tmp_path, "hit", include=("*.py",)))
    assert "keep.py" in out
    assert "skip.md" not in out
    assert "node_modules" not in out


def test_context_lines_merge_and_long_lines_truncate(tmp_path: pathlib.Path):
    (tmp_path / "a.txt").write_text(
        "one\nmatch\ntwo\n" + ("x" * 400) + "\n", encoding="utf-8"
    )
    out = run_grep(options(tmp_path, "match", context_lines=2, max_line_chars=40))
    assert "a.txt-1-one" in out
    assert "a.txt:2:1:match" in out
    assert "a.txt-3-two" in out
    assert "a.txt-4-x" in out
    assert "…" in out


def test_binary_oversized_and_unreadable_files_are_skipped(tmp_path: pathlib.Path):
    (tmp_path / "binary.dat").write_bytes(b"\x00needle")
    (tmp_path / "huge.txt").write_text("needle", encoding="utf-8")
    out = run_grep(options(tmp_path, "needle", max_file_bytes=2))
    assert "No matches." in out
    assert "Skipped" in out


def test_match_and_walk_limits(tmp_path: pathlib.Path):
    for i in range(5):
        (tmp_path / f"{i}.txt").write_text("needle\n", encoding="utf-8")
    out = run_grep(options(tmp_path, "needle", max_results=2))
    assert out.count("needle") == 2
    assert "Stopped after 2 matches" in out

    walk = run_grep(options(tmp_path, "needle", max_walk_entries=1))
    assert "Search truncated" in walk


def test_symlinks_are_not_followed(tmp_path: pathlib.Path):
    project = tmp_path / "project"
    project.mkdir()
    target = tmp_path / "outside.txt"
    target.write_text("needle\n", encoding="utf-8")
    link = project / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")

    out = run_grep(options(project, "needle"))
    assert "No matches." in out


def test_project_relative_and_extra_root_absolute(tmp_path: pathlib.Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "a.txt").write_text("needle\n", encoding="utf-8")
    out = run_grep(options(project, "needle"))
    assert "a.txt:1:1:needle" in out

    extra = tmp_path / "extra"
    extra.mkdir()
    (extra / "b.txt").write_text("needle\n", encoding="utf-8")
    out = run_grep(
        GrepOptions(
            pattern="needle",
            root=extra,
            project_root=project,
            fixed_strings=False,
            ignore_case=False,
            include=(),
            exclude=(),
            context_lines=0,
            max_results=200,
            max_file_bytes=2 * 1024 * 1024,
            max_line_chars=300,
            max_walk_entries=100_000,
        )
    )
    assert str(extra / "b.txt") in out
