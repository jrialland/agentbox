import pathlib

import pytest

from agentbox_harness.tools.filesystem import (
    FileEdit,
    FilesystemToolbox,
    PathEscapesRootError,
)


@pytest.fixture
def root(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "project"
    root.mkdir()
    return root


async def test_read_and_write_round_trip(root):
    box = FilesystemToolbox(root)
    await box.write_file("notes.txt", "hello")
    assert await box.read_text_file("notes.txt") == "hello"


async def test_read_text_file_head_and_tail(root):
    box = FilesystemToolbox(root)
    await box.write_file("f.txt", "a\nb\nc\nd")
    assert await box.read_text_file("f.txt", head=2) == "a\nb"
    assert await box.read_text_file("f.txt", tail=2) == "c\nd"
    with pytest.raises(ValueError):
        await box.read_text_file("f.txt", head=1, tail=1)


async def test_list_directory(root):
    box = FilesystemToolbox(root)
    await box.write_file("a.txt", "a")
    await box.create_directory("sub")
    await box.write_file("sub/b.txt", "b")
    listing = await box.list_directory(".")
    assert "[FILE] a.txt" in listing
    assert "[DIR] sub" in listing


async def test_list_allowed_directories(root, tmp_path):
    skill = tmp_path / "skill"
    skill.mkdir()
    box = FilesystemToolbox(root, extra_read_roots=[skill])
    listing = await box.list_allowed_directories()
    assert str(root.resolve()) in listing
    assert str(skill.resolve()) in listing


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


async def test_edit_file_matches_despite_indentation(root):
    box = FilesystemToolbox(root)
    await box.write_file("f.py", "def f():\n    return 1\n")
    await box.edit_file(
        "f.py",
        [FileEdit(old_text="def f():\n  return 1", new_text="def f():\n  return 2")],
    )
    assert (root / "f.py").read_text(encoding="utf-8") == "def f():\n    return 2\n"


async def test_edit_file_preserves_crlf(root):
    box = FilesystemToolbox(root)
    (root / "f.txt").write_bytes(b"a\r\nb\r\n")
    await box.edit_file("f.txt", [FileEdit(old_text="b", new_text="c")])
    assert (root / "f.txt").read_bytes() == b"a\r\nc\r\n"


async def test_edit_file_dry_run_returns_diff(root):
    box = FilesystemToolbox(root)
    await box.write_file("f.txt", "hello world")
    diff = await box.edit_file(
        "f.txt", [FileEdit(old_text="world", new_text="there")], dry_run=True
    )
    assert "-hello world" in diff
    assert "+hello there" in diff
    assert await box.read_text_file("f.txt") == "hello world"


async def test_edit_file_all_or_nothing(root):
    box = FilesystemToolbox(root)
    await box.write_file("f.txt", "alpha")
    with pytest.raises(ValueError):
        await box.edit_file(
            "f.txt",
            [
                FileEdit(old_text="alpha", new_text="beta"),
                FileEdit(old_text="nope", new_text="x"),
            ],
        )
    assert await box.read_text_file("f.txt") == "alpha"


async def test_create_directory(root):
    box = FilesystemToolbox(root)
    await box.create_directory("a/b/c")
    assert (root / "a/b/c").is_dir()


async def test_write_and_append_require_existing_parent(root):
    box = FilesystemToolbox(root)
    with pytest.raises(ValueError):
        await box.write_file("missing/f.txt", "x")
    with pytest.raises(ValueError):
        await box.append_file("missing/f.txt", "x")


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


async def test_move_and_copy_refuse_existing_destination(root):
    box = FilesystemToolbox(root)
    await box.write_file("a.txt", "a")
    await box.write_file("b.txt", "b")
    with pytest.raises(ValueError):
        await box.move_file("a.txt", "b.txt")
    with pytest.raises(ValueError):
        await box.copy_file("a.txt", "b.txt")


async def test_delete_file_and_guards(root):
    box = FilesystemToolbox(root)
    await box.write_file("a.txt", "a")
    await box.delete_path("a.txt")
    assert not (root / "a.txt").exists()

    await box.create_directory("full")
    await box.write_file("full/x.txt", "x")
    with pytest.raises(ValueError):
        await box.delete_path("full")
    await box.delete_path("full", recursive=True)
    assert not (root / "full").exists()
    with pytest.raises(ValueError):
        await box.delete_path(".")


async def test_search_files(root):
    box = FilesystemToolbox(root)
    await box.write_file("a.txt", "a")
    await box.create_directory("sub")
    await box.write_file("sub/b.txt", "b")
    await box.write_file("c.md", "c")
    out = await box.search_files(".", "*.txt")
    assert set(out.splitlines()) == {str(root / "a.txt"), str(root / "sub/b.txt")}


async def test_search_files_glob_and_excludes(root):
    box = FilesystemToolbox(root)
    await box.write_file("a.txt", "a")
    await box.create_directory("keep")
    await box.write_file("keep/b.txt", "b")
    await box.create_directory("skip")
    await box.write_file("skip/c.txt", "c")
    out = await box.search_files(".", "*.txt", exclude_patterns=["skip"])
    assert "a.txt" in out
    assert "b.txt" in out
    assert "c.txt" not in out


async def test_directory_tree(root):
    box = FilesystemToolbox(root)
    await box.write_file("a.txt", "a")
    await box.create_directory("sub")
    await box.write_file("sub/b.txt", "b")
    tree = await box.directory_tree(".")
    assert [n["name"] for n in tree] == ["a.txt", "sub"]


async def test_directory_tree_json_depth_and_excludes(root):
    box = FilesystemToolbox(root)
    await box.write_file("a.txt", "a")
    await box.create_directory("sub")
    await box.write_file("sub/b.txt", "b")
    tree = await box.directory_tree(".", exclude_patterns=["sub"])
    assert [n["name"] for n in tree] == ["a.txt"]
    shallow = await box.directory_tree(".", depth=1)
    assert all("children" not in n for n in shallow)


async def test_list_directory_with_sizes_sorts_by_size(root):
    box = FilesystemToolbox(root)
    await box.write_file("small.txt", "a")
    await box.write_file("big.txt", "abcdef")
    names = await box.list_directory_with_sizes(".", sort_by="size")
    assert names.index("big.txt") < names.index("small.txt")
    assert "Total: 2 files" in names


async def test_get_file_info_reports_type_and_links(root):
    box = FilesystemToolbox(root)
    await box.write_file("a.txt", "abc")
    info = await box.get_file_info("a.txt")
    assert info["type"] == "file"
    assert info["size"] == 3
    assert info["hardLinks"] == 1


async def test_read_media_file_downscales_image_to_png(root):
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (4000, 2000), "red").save(buf, format="PNG")
    (root / "big.png").write_bytes(buf.getvalue())

    box = FilesystemToolbox(
        root, media_max_dimension=100, media_max_bytes=10_000_000
    )
    result = await box.read_media_file("big.png")
    assert "image/png" in result.return_value  # ty: ignore[unsupported-operator]
    content = result.content[0]  # ty: ignore[not-subscriptable]
    assert content.media_type == "image/png"  # ty: ignore[missing-union-attribute]
    with Image.open(BytesIO(content.data)) as img:  # ty: ignore[missing-union-attribute]
        assert max(img.size) <= 100


async def test_read_media_file_non_image_uses_mime(root):
    box = FilesystemToolbox(root)
    await box.write_file("note.txt", "hi")
    result = await box.read_media_file("note.txt")
    content = result.content[0]  # ty: ignore[not-subscriptable]
    assert content.media_type.startswith("text/plain")  # ty: ignore[missing-union-attribute]


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


async def test_extra_write_root_allows_file_operations(root, tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    box = FilesystemToolbox(root, extra_write_roots=[external])
    target = str(external / "x.txt")
    await box.write_file(target, "hello")
    assert await box.read_text_file(target) == "hello"
    await box.edit_file(target, [FileEdit(old_text="hello", new_text="bye")])
    assert await box.read_text_file(target) == "bye"
    await box.delete_path(target)
    assert not (external / "x.txt").exists()


async def test_extra_write_root_still_blocks_other_paths(root, tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    box = FilesystemToolbox(root, extra_write_roots=[external])
    with pytest.raises(PathEscapesRootError):
        await box.write_file(str(tmp_path / "outside.txt"), "nope")


async def test_extra_write_root_listing_and_delete_guard(root, tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    box = FilesystemToolbox(root, extra_write_roots=[external])
    assert str(external.resolve()) in await box.list_allowed_directories()
    with pytest.raises(ValueError):
        await box.delete_path(str(external), recursive=True)
