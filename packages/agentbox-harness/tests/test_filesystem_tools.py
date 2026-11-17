import pathlib

import pytest

from agentbox_harness.tools.filesystem import FilesystemToolbox, PathEscapesRootError


@pytest.fixture
def root(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "project"


async def test_read_and_write_round_trip(root):
    box = FilesystemToolbox(root)
    await box.write_file("notes.txt", "hello")
    assert await box.read_text_file("notes.txt") == "hello"


async def test_list_directory(root):
    box = FilesystemToolbox(root)
    await box.write_file("a.txt", "a")
    await box.write_file("sub/b.txt", "b")
    names = sorted(await box.list_directory("."))
    assert "a.txt" in names
    assert "sub" in names


async def test_escape_is_rejected(root, tmp_path):
    box = FilesystemToolbox(root)
    with pytest.raises(PathEscapesRootError):
        await box.read_text_file("../secret.txt")


async def test_absolute_escape_is_rejected(root, tmp_path):
    box = FilesystemToolbox(root)
    with pytest.raises(PathEscapesRootError):
        await box.write_file(str(tmp_path / "elsewhere.txt"), "nope")
