import pathlib

import pytest

from agentbox_harness.tools.filesystem import (
    FileEdit,
    FilesystemToolbox,
    PathEscapesRootError,
)


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


async def test_read_multiple_files(root):
    box = FilesystemToolbox(root)
    await box.write_file("a.txt", "A")
    await box.write_file("b.txt", "B")
    out = await box.read_multiple_files(["a.txt", "b.txt"])
    assert "--- a.txt ---" in out
    assert "A" in out
    assert "B" in out


async def test_append_file(root):
    box = FilesystemToolbox(root)
    await box.write_file("log.txt", "a")
    await box.append_file("log.txt", "b")
    assert await box.read_text_file("log.txt") == "ab"


async def test_edit_file(root):
    box = FilesystemToolbox(root)
    await box.write_file("f.txt", "hello world")
    await box.edit_file("f.txt", [FileEdit(old_text="world", new_text="there")])
    assert await box.read_text_file("f.txt") == "hello there"


async def test_edit_file_dry_run(root):
    box = FilesystemToolbox(root)
    await box.write_file("f.txt", "hello world")
    await box.edit_file(
        "f.txt", [FileEdit(old_text="world", new_text="there")], dry_run=True
    )
    assert await box.read_text_file("f.txt") == "hello world"


async def test_edit_file_missing_old_text_raises(root):
    box = FilesystemToolbox(root)
    await box.write_file("f.txt", "hello")
    with pytest.raises(ValueError):
        await box.edit_file("f.txt", [FileEdit(old_text="nope", new_text="x")])


async def test_create_directory(root):
    box = FilesystemToolbox(root)
    await box.create_directory("a/b/c")
    assert (root / "a/b/c").is_dir()


async def test_move_file(root):
    box = FilesystemToolbox(root)
    await box.write_file("src.txt", "data")
    await box.move_file("src.txt", "dst.txt")
    assert not (root / "src.txt").exists()
    assert (root / "dst.txt").read_text() == "data"


async def test_copy_file(root):
    box = FilesystemToolbox(root)
    await box.write_file("src.txt", "data")
    await box.copy_file("src.txt", "dst.txt")
    assert (root / "src.txt").exists()
    assert (root / "dst.txt").read_text() == "data"


async def test_search_files(root):
    box = FilesystemToolbox(root)
    await box.write_file("a.txt", "a")
    await box.write_file("sub/b.txt", "b")
    await box.write_file("c.md", "c")
    results = await box.search_files(".", "*.txt")
    assert set(results) == {"a.txt", "sub/b.txt"}


async def test_directory_tree(root):
    box = FilesystemToolbox(root)
    await box.write_file("a.txt", "a")
    await box.write_file("sub/b.txt", "b")
    tree = await box.directory_tree(".")
    assert "a.txt" in tree
    assert "b.txt" in tree


def test_reads_extra_root_but_blocks_write(tmp_path):
    import asyncio

    from agentbox_harness.tools.filesystem import FilesystemToolbox

    root = tmp_path / "proj"
    root.mkdir()
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "ref.md").write_text("hi", encoding="utf-8")
    box = FilesystemToolbox(root, extra_read_roots=[skill])
    assert asyncio.run(box.read_text_file(str(skill / "ref.md"))) == "hi"
    from agentbox_harness.tools.filesystem import PathEscapesRootError

    try:
        asyncio.run(box.write_file(str(skill / "x.txt"), "x"))
    except PathEscapesRootError:
        pass
    else:
        raise AssertionError("write outside root should fail")
