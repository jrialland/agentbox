import pathlib

import pytest

from agentbox_api import project_instructions


def test_loads_project_root_file(tmp_path: pathlib.Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text("Run tests before commit.", encoding="utf-8")

    loaded = project_instructions.read_instruction_file(
        project / "AGENTS.md",
        boundary=project,
        source="AGENTS.md",
        scope="project",
        max_bytes=project_instructions.MAX_INSTRUCTION_BYTES,
    )

    assert loaded is not None
    assert loaded.content == "Run tests before commit."
    assert loaded.truncated is False


def test_ignores_missing_and_empty_files(tmp_path: pathlib.Path):
    project = tmp_path / "project"
    project.mkdir()
    assert (
        project_instructions.read_instruction_file(
            project / "AGENTS.md",
            boundary=project,
            source="AGENTS.md",
            scope="project",
            max_bytes=project_instructions.MAX_INSTRUCTION_BYTES,
        )
        is None
    )
    (project / "AGENTS.md").write_text("   \n", encoding="utf-8")
    assert (
        project_instructions.read_instruction_file(
            project / "AGENTS.md",
            boundary=project,
            source="AGENTS.md",
            scope="project",
            max_bytes=project_instructions.MAX_INSTRUCTION_BYTES,
        )
        is None
    )


def test_truncates_on_utf8_boundary_and_marks_truncated(tmp_path: pathlib.Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text("é" * 40, encoding="utf-8")

    loaded = project_instructions.read_instruction_file(
        project / "AGENTS.md",
        boundary=project,
        source="AGENTS.md",
        scope="project",
        max_bytes=31,
    )

    assert loaded is not None
    assert loaded.truncated is True
    assert len(loaded.content.encode("utf-8")) <= 31
    assert loaded.content.startswith("é")


def test_rejects_symlink_escape(tmp_path: pathlib.Path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    link = project / "AGENTS.md"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")

    assert (
        project_instructions.read_instruction_file(
            link,
            boundary=project,
            source="AGENTS.md",
            scope="project",
            max_bytes=project_instructions.MAX_INSTRUCTION_BYTES,
        )
        is None
    )


def test_read_failure_uses_last_known_content(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
    project = tmp_path / "project"
    project.mkdir()
    agents = project / "AGENTS.md"
    agents.write_text("known guidance", encoding="utf-8")
    args = dict(
        boundary=project,
        source="AGENTS.md",
        scope="project",
        max_bytes=project_instructions.MAX_INSTRUCTION_BYTES,
    )
    first = project_instructions.read_instruction_file(agents, **args)
    assert first is not None and first.content == "known guidance"

    original_read = pathlib.Path.read_bytes

    def failing_read(self):
        if self == agents:
            raise OSError("temporary")
        return original_read(self)

    monkeypatch.setattr(pathlib.Path, "read_bytes", failing_read)
    second = project_instructions.read_instruction_file(agents, **args)
    assert second is not None
    assert second.content == "known guidance"


def test_global_path_uses_home(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        project_instructions,
        "global_instructions_path",
        lambda: tmp_path / "AGENTS.md",
    )
    (tmp_path / "AGENTS.md").write_text("global", encoding="utf-8")
    loaded = project_instructions.load_global_instructions()
    assert loaded is not None and loaded.content == "global"
    assert loaded.source == "~/AGENTS.md"
