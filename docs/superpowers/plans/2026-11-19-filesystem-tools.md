# File System Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a full feature set of filesystem tools modelled on `@modelcontextprotocol/server-filesystem`, plus guarded delete, PNG image optimization, and post-tool hooks.

**Architecture:** Expand `FilesystemToolbox` in the harness with reference-faithful read/write tools, basic path containment, 15 s/100k bounds, and an image pipeline. Add hooks to `ToolRegistry`. Register every tool in `runtime.build_registry` with read/write flags, expose them in the agent UI, and keep native tools opt-in.

**Tech Stack:** Python 3.12, uv, pydantic-ai 2.69 (`ToolReturn`, `BinaryContent`), Pillow, pytest (asyncio auto), React/TypeScript.

## Global Constraints

- Tool names exactly: `read_text_file`, `read_file`, `read_media_file`, `read_multiple_files`, `list_directory`, `list_directory_with_sizes`, `directory_tree`, `search_files`, `get_file_info`, `list_allowed_directories`, `write_file`, `append_file`, `edit_file`, `create_directory`, `move_file`, `copy_file`, `delete_path`.
- Read tools use `required_flags=("read",)`; mutating tools use `required_flags=("write",)`; empty `tool_bindings` means **no** native tools.
- Basic containment only: resolve real paths and require containment; no Windows ADS / reserved-name / trailing-dot guards.
- `CALL_TIMEOUT_SECONDS = 15.0`; `MAX_WALK_ENTRIES = 100_000`.
- Media defaults: `media_max_dimension=1568`, `media_max_bytes=1_500_000`.
- Never log secrets or file contents.
- Run `uv run ruff check packages`, `uv run ty check packages`, and the package test suites before each commit.

---

### Task 1: Tool result hooks in `ToolRegistry`

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/registry.py`
- Test: `packages/agentbox-harness/tests/test_tool_registry.py`

**Interfaces:**
- Produces: `ToolHookContext(tool_name: str, args: dict, root: object, result: object)`, `ToolHook = Callable[[ToolHookContext], Awaitable[str | None]]`, `ToolRegistry(hooks=None, root=None)`.

- [ ] **Step 1: Write failing tests**

Append to `test_tool_registry.py`:

```python
async def test_hook_appends_to_string_result():
    async def hook(ctx):
        return f"hooked {ctx.tool_name} {ctx.args['path']}"

    reg = ToolRegistry(hooks=[hook])
    reg.register_native("read_file", read_file, required_flags=("read",))
    tools = reg.select_tools(Mode(name="ask", flags={}))
    assert await tools[0](path="a.txt") == "data\n\nhooked read_file a.txt"
    assert tools[0].__name__ == "read_file"


async def test_hook_error_is_isolated():
    async def boom(ctx):
        raise RuntimeError("nope")

    reg = ToolRegistry(hooks=[boom])
    reg.register_native("read_file", read_file)
    tools = reg.select_tools(Mode(name="ask", flags={}))
    assert await tools[0](path="a.txt") == "data"


async def test_hook_does_not_modify_non_string_result():
    async def value(path: str) -> dict:
        return {"path": path}

    async def hook(ctx):
        return "extra"

    reg = ToolRegistry(hooks=[hook])
    reg.register_native("value", value)
    tools = reg.select_tools(Mode(name="ask", flags={}))
    assert await tools[0](path="a") == {"path": "a"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_tool_registry.py -q`
Expected: FAIL (`ToolRegistry` does not accept `hooks`).

- [ ] **Step 3: Implement hooks**

Replace `registry.py` with:

```python
import functools
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from loguru import logger

from agentbox_harness.spec import Mode


@dataclass
class ToolHookContext:
    tool_name: str
    args: dict
    root: object
    result: object


ToolHook = Callable[[ToolHookContext], Awaitable[str | None]]


@dataclass
class _Entry:
    callable: Callable
    required_flags: tuple[str, ...] = ()


class ToolRegistry:
    def __init__(self, hooks: list[ToolHook] | None = None, root=None) -> None:
        self._native: dict[str, _Entry] = {}
        self._hooks = list(hooks or [])
        self._root = root

    def register_native(
        self,
        name: str,
        callable: Callable,
        required_flags: tuple[str, ...] = (),
    ) -> None:
        fn = callable
        if self._hooks:
            original = callable

            @functools.wraps(original)
            async def wrapped(*args, **kwargs):
                result = await original(*args, **kwargs)
                try:
                    bound = inspect.signature(original).bind(*args, **kwargs)
                    call_args = dict(bound.arguments)
                except TypeError:
                    call_args = dict(kwargs)
                extras: list[str] = []
                for hook in self._hooks:
                    try:
                        extra = await hook(
                            ToolHookContext(
                                tool_name=name,
                                args=call_args,
                                root=self._root,
                                result=result,
                            )
                        )
                    except Exception:
                        logger.exception("tool hook failed tool={}", name)
                        continue
                    if extra:
                        extras.append(extra)
                if extras and isinstance(result, str):
                    return "\n\n".join([result, *extras])
                return result

            fn = wrapped
        self._native[name] = _Entry(fn, required_flags)

    def select_tools(
        self, mode: Mode, names: set[str] | None = None
    ) -> list[Callable]:
        result = []
        for name, entry in self._native.items():
            if names is not None and name not in names:
                continue
            if all(mode.allows(f) for f in entry.required_flags):
                result.append(entry.callable)
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/agentbox-harness/tests/test_tool_registry.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/tools/registry.py packages/agentbox-harness/tests/test_tool_registry.py
git commit -m "feat(harness): add post-tool result hooks"
```

---

### Task 2: Containment, timeouts, and read/list tools

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/filesystem.py`
- Test: `packages/agentbox-harness/tests/test_filesystem_tools.py`

**Interfaces:**
- Produces: async `_resolve(path, write=False)`, `read_text_file(path, head=None, tail=None)`, `read_file(path)`, `read_multiple_files(paths)`, `list_directory(path) -> str`, `list_allowed_directories() -> str`.

- [ ] **Step 1: Write failing tests**

Append to `test_filesystem_tools.py`:

```python
async def test_read_text_file_head_and_tail(root):
    box = FilesystemToolbox(root)
    await box.write_file("f.txt", "a\nb\nc\nd")
    assert await box.read_text_file("f.txt", head=2) == "a\nb"
    assert await box.read_text_file("f.txt", tail=2) == "c\nd"
    with pytest.raises(ValueError):
        await box.read_text_file("f.txt", head=1, tail=1)


async def test_list_directory_marks_types(root):
    box = FilesystemToolbox(root)
    await box.write_file("a.txt", "a")
    await box.create_directory("sub")
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
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-harness/tests/test_filesystem_tools.py -q`
Expected: FAIL (`TypeError` for `head`/`tail`, listing format).

- [ ] **Step 3: Implement**

At the top of `filesystem.py`, add:

```python
import asyncio
import stat

CALL_TIMEOUT_SECONDS = 15.0
MAX_WALK_ENTRIES = 100_000
```

In `FilesystemToolbox`, add:

```python
    async def _blocking(self, fn, *args, **kwargs):
        return await asyncio.wait_for(
            asyncio.to_thread(fn, *args, **kwargs), CALL_TIMEOUT_SECONDS
        )

    async def _resolve(self, path: str, *, write: bool = False) -> pathlib.Path:
        def _do() -> pathlib.Path:
            candidate = pathlib.Path(path)
            p = (
                candidate if candidate.is_absolute() else self.root_dir / candidate
            ).resolve()
            roots = [self.root_dir] if write else self._read_roots
            if not any(p == r or r in p.parents for r in roots):
                logger.warning("path escapes root path={} root={}", path, self.root_dir)
                raise PathEscapesRootError(path)
            return p

        return await self._blocking(_do)

    async def read_text_file(
        self, path: str, head: int | None = None, tail: int | None = None
    ) -> str:
        if head is not None and tail is not None:
            raise ValueError("head and tail are mutually exclusive")
        p = await self._resolve(path)
        if not stat.S_ISREG((await self._blocking(p.stat)).st_mode):
            raise ValueError(f"Not a regular file: {path}")
        text = await self._blocking(lambda: p.read_text(encoding="utf-8"))
        if head is not None:
            return "\n".join(text.splitlines()[:head])
        if tail is not None:
            return "\n".join(text.splitlines()[-tail:]) if tail else ""
        return text

    async def read_file(self, path: str) -> str:
        return await self.read_text_file(path)

    async def read_multiple_files(self, paths: list[str]) -> str:
        parts = []
        for path in paths:
            try:
                parts.append(f"--- {path} ---\n{await self.read_text_file(path)}")
            except Exception as exc:
                parts.append(f"--- {path} ---\nError: {exc}")
        return "\n".join(parts)

    async def list_directory(self, path: str) -> str:
        p = await self._resolve(path)
        entries = await self._blocking(lambda: sorted(p.iterdir(), key=lambda e: e.name))
        return "\n".join(
            f"[{'DIR' if e.is_dir() else 'FILE'}] {e.name}" for e in entries
        )

    async def list_allowed_directories(self) -> str:
        return "\n".join(str(r) for r in self._read_roots)
```

Remove the old `_resolve`, `read_text_file`, `read_multiple_files`, `list_directory`, and `list_allowed_directories` stubs so only one definition remains. Update every other method to `await self._resolve(...)`.

Also update the existing `test_list_directory`:

```python
async def test_list_directory(root):
    box = FilesystemToolbox(root)
    await box.write_file("a.txt", "a")
    await box.create_directory("sub")
    await box.write_file("sub/b.txt", "b")
    listing = await box.list_directory(".")
    assert "[FILE] a.txt" in listing
    assert "[DIR] sub" in listing
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest packages/agentbox-harness/tests/test_filesystem_tools.py -q`
Expected: PASS (later tests still reference old behaviour; fix them in Tasks 4/5).

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/tools/filesystem.py packages/agentbox-harness/tests/test_filesystem_tools.py
git commit -m "feat(harness): containment, timeouts, read/list tools"
```

---

### Task 3: Sizes, metadata, tree, and search

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/filesystem.py`
- Test: `packages/agentbox-harness/tests/test_filesystem_tools.py`

**Interfaces:**
- Produces: `list_directory_with_sizes(path, sort_by="name") -> str`, `get_file_info(path) -> dict`, `directory_tree(path, exclude_patterns=None, depth=None) -> list[dict]`, `search_files(path, pattern, exclude_patterns=None) -> str`.

- [ ] **Step 1: Write failing tests**

Append:

```python
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


async def test_directory_tree_json_depth_and_excludes(root):
    box = FilesystemToolbox(root)
    await box.write_file("a.txt", "a")
    await box.create_directory("sub")
    await box.write_file("sub/b.txt", "b")
    tree = await box.directory_tree(".", exclude_patterns=["sub"])
    assert [n["name"] for n in tree] == ["a.txt"]
    shallow = await box.directory_tree(".", depth=1)
    assert all("children" not in n for n in shallow)


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
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-harness/tests/test_filesystem_tools.py -q`
Expected: FAIL (methods missing / tree returns text).

- [ ] **Step 3: Implement**

Add imports `import fnmatch`, `import os`. Add module helper:

```python
def _excluded(rel: str, name: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if "/" not in pat and "*" not in pat:
            if name == pat:
                return True
        else:
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat):
                return True
            if pat.endswith("/**") and fnmatch.fnmatch(rel, pat[:-3]):
                return True
    return False
```

Add/modify methods:

```python
    async def list_directory_with_sizes(
        self, path: str, sort_by: str = "name"
    ) -> str:
        p = await self._resolve(path)

        def _rows():
            rows = []
            for e in p.iterdir():
                try:
                    size = e.stat().st_size if e.is_file() else 0
                except OSError:
                    size = None
                rows.append((e.name, e.is_dir(), size))
            if sort_by == "size":
                rows.sort(key=lambda r: (r[2] is None, -(r[2] or 0), r[0]))
            else:
                rows.sort(key=lambda r: r[0])
            return rows

        rows = await self._blocking(_rows)
        lines, files, dirs, total = [], 0, 0, 0
        for name, is_dir, size in rows:
            if is_dir:
                dirs += 1
                lines.append(f"[DIR] {name}")
            else:
                files += 1
                if size is None:
                    lines.append(f"[FILE] {name} (unknown)")
                else:
                    total += size
                    lines.append(f"[FILE] {name} ({size} B)")
        lines.append(f"Total: {files} files, {dirs} directories, {total} bytes")
        return "\n".join(lines)

    async def get_file_info(self, path: str) -> dict:
        p = await self._resolve(path)
        st = await self._blocking(p.stat)
        return {
            "path": str(p),
            "size": st.st_size,
            "created": st.st_ctime,
            "modified": st.st_mtime,
            "accessed": st.st_atime,
            "type": "directory" if p.is_dir() else "file",
            "permissions": stat.filemode(st.st_mode),
            "hardLinks": st.st_nlink,
        }

    async def directory_tree(
        self,
        path: str,
        exclude_patterns: list[str] | None = None,
        depth: int | None = None,
    ) -> list[dict]:
        p = await self._resolve(path)
        patterns = exclude_patterns or []
        counter = 0

        def build(dir_path: pathlib.Path, prefix: str, level: int) -> list[dict]:
            nonlocal counter
            nodes = []
            for entry in sorted(dir_path.iterdir(), key=lambda e: e.name):
                counter += 1
                if counter > MAX_WALK_ENTRIES:
                    raise ValueError(f"stopped after visiting {MAX_WALK_ENTRIES} entries")
                rel = f"{prefix}/{entry.name}".lstrip("/")
                if _excluded(rel, entry.name, patterns):
                    continue
                if entry.is_dir():
                    node: dict = {"name": entry.name, "type": "directory"}
                    if depth is None or level < depth:
                        node["children"] = build(entry, rel, level + 1)
                    nodes.append(node)
                else:
                    nodes.append({"name": entry.name, "type": "file"})
            return nodes

        return await self._blocking(build, p, "", 1)

    async def search_files(
        self,
        path: str,
        pattern: str,
        exclude_patterns: list[str] | None = None,
    ) -> str:
        p = await self._resolve(path)
        patterns = exclude_patterns or []

        def walk():
            counter = 0
            matches: list[str] = []
            errors: list[str] = []

            def onerror(err):
                errors.append(f"{err.filename}: {err.strerror}")

            for dirpath, dirnames, filenames in os.walk(p, onerror=onerror):
                rel_dir = pathlib.Path(dirpath).relative_to(p).as_posix()
                kept = []
                for d in dirnames:
                    rel = d if rel_dir == "." else f"{rel_dir}/{d}"
                    counter += 1
                    if counter > MAX_WALK_ENTRIES:
                        raise ValueError(
                            f"stopped after visiting {MAX_WALK_ENTRIES} entries"
                        )
                    if not _excluded(rel, d, patterns):
                        kept.append(d)
                dirnames[:] = kept
                for f in filenames:
                    rel = f if rel_dir == "." else f"{rel_dir}/{f}"
                    counter += 1
                    if counter > MAX_WALK_ENTRIES:
                        raise ValueError(
                            f"stopped after visiting {MAX_WALK_ENTRIES} entries"
                        )
                    if _excluded(rel, f, patterns):
                        continue
                    if fnmatch.fnmatch(rel, pattern):
                        matches.append(str(pathlib.Path(dirpath) / f))
            return matches, errors

        matches, errors = await self._blocking(walk)
        out = "\n".join(sorted(matches))
        if errors:
            out += "\nNote: incomplete search:\n" + "\n".join(errors)
        return out
```

Remove the old `search_files` and `directory_tree` definitions. Update the existing tests to the new shapes:

```python
async def test_search_files(root):
    box = FilesystemToolbox(root)
    await box.write_file("a.txt", "a")
    await box.create_directory("sub")
    await box.write_file("sub/b.txt", "b")
    await box.write_file("c.md", "c")
    out = await box.search_files(".", "*.txt")
    assert set(out.splitlines()) == {str(root / "a.txt"), str(root / "sub/b.txt")}


async def test_directory_tree(root):
    box = FilesystemToolbox(root)
    await box.write_file("a.txt", "a")
    await box.create_directory("sub")
    await box.write_file("sub/b.txt", "b")
    tree = await box.directory_tree(".")
    assert [n["name"] for n in tree] == ["a.txt", "sub"]
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest packages/agentbox-harness/tests/test_filesystem_tools.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/tools/filesystem.py packages/agentbox-harness/tests/test_filesystem_tools.py
git commit -m "feat(harness): sizes, metadata, JSON tree, bounded search"
```

---

### Task 4: Mutating semantics and guarded delete

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/filesystem.py`
- Test: `packages/agentbox-harness/tests/test_filesystem_tools.py`

**Interfaces:**
- Produces: `write_file`, `append_file`, `create_directory`, `move_file`, `copy_file`, `delete_path(path, recursive=False)` with the semantics below.

- [ ] **Step 1: Write failing tests**

Append:

```python
async def test_write_and_append_require_existing_parent(root):
    box = FilesystemToolbox(root)
    with pytest.raises(ValueError):
        await box.write_file("missing/f.txt", "x")
    with pytest.raises(ValueError):
        await box.append_file("missing/f.txt", "x")


async def test_write_and_append_keep_content(root):
    box = FilesystemToolbox(root)
    await box.write_file("log.txt", "a")
    await box.append_file("log.txt", "b")
    assert await box.read_text_file("log.txt") == "ab"


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
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-harness/tests/test_filesystem_tools.py -q`
Expected: FAIL (write currently creates parents; move overwrites; delete missing).

- [ ] **Step 3: Implement**

Replace the mutating methods with:

```python
    async def write_file(self, path: str, content: str) -> str:
        p = await self._resolve(path, write=True)
        if not p.parent.exists():
            raise ValueError(f"Parent directory does not exist: {p.parent}")
        await self._blocking(lambda: p.write_text(content, encoding="utf-8"))
        return f"Wrote {len(content)} bytes to {path}"

    async def append_file(self, path: str, content: str) -> str:
        p = await self._resolve(path, write=True)
        if not p.parent.exists():
            raise ValueError(f"Parent directory does not exist: {p.parent}")
        with p.open("a", encoding="utf-8") as f:
            f.write(content)
        return f"Appended {len(content)} bytes to {path}"

    async def create_directory(self, path: str) -> str:
        p = await self._resolve(path, write=True)
        await self._blocking(lambda: p.mkdir(parents=True, exist_ok=True))
        return f"Created directory {path}"

    async def move_file(self, source: str, destination: str) -> str:
        src = await self._resolve(source, write=True)
        dst = await self._resolve(destination, write=True)
        if dst.exists():
            raise ValueError(f"Destination exists: {destination}")
        if not dst.parent.exists():
            raise ValueError(f"Parent directory does not exist: {dst.parent}")
        if src.is_dir() and os.stat(src).st_dev != os.stat(dst.parent).st_dev:
            raise ValueError("Cannot move a directory across filesystems")
        await self._blocking(shutil.move, str(src), str(dst))
        return f"Moved {source} to {destination}"

    async def copy_file(self, source: str, destination: str) -> str:
        src = await self._resolve(source, write=True)
        dst = await self._resolve(destination, write=True)
        if not src.is_file():
            raise ValueError("Source is not a regular file")
        if dst.exists():
            raise ValueError(f"Destination exists: {destination}")
        if not dst.parent.exists():
            raise ValueError(f"Parent directory does not exist: {dst.parent}")
        await self._blocking(shutil.copy2, str(src), str(dst))
        return f"Copied {source} to {destination}"

    async def delete_path(self, path: str, recursive: bool = False) -> str:
        candidate = pathlib.Path(path)
        target = candidate if candidate.is_absolute() else self.root_dir / candidate
        parent = target.parent.resolve()
        if not (parent == self.root_dir or self.root_dir in parent.parents):
            raise PathEscapesRootError(path)
        if target.resolve() == self.root_dir:
            raise ValueError("Refusing to delete an allowed root")

        def _delete():
            if target.is_symlink() or target.is_file():
                target.unlink()
            elif target.is_dir():
                if any(target.iterdir()) and not recursive:
                    raise ValueError("Directory is not empty; pass recursive=true")
                if recursive:
                    shutil.rmtree(target)
                else:
                    target.rmdir()
            else:
                raise FileNotFoundError(path)

        await self._blocking(_delete)
        return f"Deleted {path}"
```

Update `test_list_directory` and other existing tests to call `await box.create_directory("sub")` before `write_file("sub/b.txt")`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest packages/agentbox-harness/tests/test_filesystem_tools.py -q`
Expected: PASS (except edit tests updated in Task 5).

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/tools/filesystem.py packages/agentbox-harness/tests/test_filesystem_tools.py
git commit -m "feat(harness): reference write semantics and guarded delete"
```

---

### Task 5: Fuzzy `edit_file` with CRLF and diff

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/filesystem.py`
- Test: `packages/agentbox-harness/tests/test_filesystem_tools.py`

**Interfaces:**
- Produces: `edit_file(path, edits: list[FileEdit], dry_run=False) -> str` with exact-first, whitespace-normalized line matching, indentation preservation, CRLF preservation, all-or-nothing, and a unified diff on dry run.

- [ ] **Step 1: Write failing tests**

Append:

```python
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
            [FileEdit(old_text="alpha", new_text="beta"), FileEdit(old_text="nope", new_text="x")],
        )
    assert await box.read_text_file("f.txt") == "alpha"
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-harness/tests/test_filesystem_tools.py -q -k edit`
Expected: FAIL (indentation fuzz and CRLF not supported by the old exact replace).

- [ ] **Step 3: Implement**

Add `from difflib import unified_diff` at the top and module helper:

```python
def _apply_edit(text: str, edit: FileEdit, newline: str) -> str:
    if edit.old_text in text:
        return text.replace(edit.old_text, edit.new_text, 1)
    old_norm = edit.old_text.replace("\r\n", "\n").replace("\r", "\n")
    text_norm = text.replace("\r\n", "\n").replace("\r", "\n")
    old_lines = old_norm.split("\n")
    text_lines = text_norm.split("\n")
    n = len(old_lines)
    target = [line.strip() for line in old_lines]
    for i in range(len(text_lines) - n + 1):
        window = text_lines[i : i + n]
        if [line.strip() for line in window] == target:
            indent = window[0][: len(window[0]) - len(window[0].lstrip())]
            new_lines = (
                edit.new_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            )
            new_lines = [indent + line.lstrip() if line.strip() else line for line in new_lines]
            return newline.join(text_lines[:i] + new_lines + text_lines[i + n :])
    raise ValueError(f"old_text not found: {edit.old_text!r}")
```

Replace `edit_file` with:

```python
    async def edit_file(
        self,
        path: str,
        edits: list[FileEdit],
        dry_run: bool = False,
    ) -> str:
        p = await self._resolve(path, write=True)
        raw = await self._blocking(lambda: p.read_text(encoding="utf-8"))
        newline = "\r\n" if "\r\n" in raw else ("\r" if "\r" in raw else "\n")
        updated = raw
        for edit in edits:
            updated = _apply_edit(updated, edit, newline)
        if dry_run:
            diff = "".join(
                unified_diff(
                    raw.splitlines(True),
                    updated.splitlines(True),
                    fromfile=path,
                    tofile=path,
                )
            )
            return diff or "No changes"
        await self._blocking(
            lambda: p.write_text(updated, encoding="utf-8", newline="")
        )
        return f"Edited {path}"
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest packages/agentbox-harness/tests/test_filesystem_tools.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/tools/filesystem.py packages/agentbox-harness/tests/test_filesystem_tools.py
git commit -m "feat(harness): fuzzy edit_file with CRLF and diff"
```

---

### Task 6: Image-optimizing `read_media_file`

**Files:**
- Modify: `packages/agentbox-harness/pyproject.toml`
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/filesystem.py`
- Test: `packages/agentbox-harness/tests/test_filesystem_tools.py`

**Interfaces:**
- Produces: `read_media_file(path) -> ToolReturn` (summary text + `BinaryContent`).

- [ ] **Step 1: Add Pillow**

Add `"pillow>=10",` to the harness `dependencies`, then run `uv sync`.

- [ ] **Step 2: Write failing tests**

Append:

```python
async def test_read_media_file_downscales_image_to_png(root):
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (4000, 2000), "red").save(buf, format="PNG")
    (root / "big.png").write_bytes(buf.getvalue())

    box = FilesystemToolbox(root, media_max_dimension=100, media_max_bytes=10_000_000)
    result = await box.read_media_file("big.png")
    assert "image/png" in result.return_value
    content = result.content[0]
    assert content.media_type == "image/png"
    with Image.open(BytesIO(content.data)) as img:
        assert max(img.size) <= 100


async def test_read_media_file_non_image_uses_mime(root):
    box = FilesystemToolbox(root)
    await box.write_file("note.txt", "hi")
    result = await box.read_media_file("note.txt")
    assert result.content[0].media_type.startswith("text/plain")
```

- [ ] **Step 3: Implement**

Add imports:

```python
import io
import mimetypes

from pydantic_ai.messages import BinaryContent
from pydantic_ai.tools import ToolReturn
from PIL import Image
```

Add constructor params and method:

```python
    def __init__(
        self,
        root_dir: pathlib.Path,
        extra_read_roots: list[pathlib.Path] | None = None,
        media_max_dimension: int = 1568,
        media_max_bytes: int = 1_500_000,
    ):
        self.root_dir = pathlib.Path(root_dir).resolve()
        self._read_roots = [
            self.root_dir,
            *[pathlib.Path(r).resolve() for r in (extra_read_roots or [])],
        ]
        self.media_max_dimension = media_max_dimension
        self.media_max_bytes = media_max_bytes

    def _optimize_image(self, data: bytes) -> tuple[bytes, int, int]:
        with Image.open(io.BytesIO(data)) as image:
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            if max(image.size) > self.media_max_dimension:
                image.thumbnail(
                    (self.media_max_dimension, self.media_max_dimension),
                    Image.LANCZOS,
                )
            while True:
                buf = io.BytesIO()
                image.save(buf, format="PNG", optimize=True)
                out = buf.getvalue()
                if len(out) <= self.media_max_bytes or max(image.size) <= 32:
                    return out, image.width, image.height
                image = image.resize(
                    (max(1, int(image.width * 0.8)), max(1, int(image.height * 0.8))),
                    Image.LANCZOS,
                )

    async def read_media_file(self, path: str) -> ToolReturn:
        p = await self._resolve(path)
        if not p.is_file():
            raise ValueError(f"Not a regular file: {path}")
        data = await self._blocking(lambda: p.read_bytes())
        media_type = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        if media_type.startswith("image/"):
            try:
                png, width, height = await self._blocking(self._optimize_image, data)
            except Exception:
                return ToolReturn(
                    f"{path}: {len(data)} bytes, {media_type}",
                    content=[BinaryContent(data=data, media_type=media_type)],
                )
            return ToolReturn(
                f"{path}: {width}x{height}, {len(png)} bytes, image/png",
                content=[BinaryContent(data=png, media_type="image/png")],
            )
        return ToolReturn(
            f"{path}: {len(data)} bytes, {media_type}",
            content=[BinaryContent(data=data, media_type=media_type)],
        )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest packages/agentbox-harness/tests/test_filesystem_tools.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/pyproject.toml uv.lock packages/agentbox-harness/src/agentbox_harness/tools/filesystem.py packages/agentbox-harness/tests/test_filesystem_tools.py
git commit -m "feat(harness): image-optimizing read_media_file"
```

---

### Task 7: Register every tool and thread media settings

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/runtime.py`
- Modify: `packages/agentbox-api/src/agentbox_api/config.py`
- Modify: `packages/agentbox-api/src/agentbox_api/skills.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`, `acp_server.py`, `a2a_executor.py` (call sites of `prepare_agent`)
- Test: create `packages/agentbox-api/tests/test_runtime_tools.py`

**Interfaces:**
- Produces: `build_registry(project_root, extra_read_roots=None, extra_tools=None, hooks=None, media_max_dimension=1568, media_max_bytes=1_500_000)`; `Settings.media_max_dimension`, `Settings.media_max_bytes`; `prepare_agent(..., media_max_dimension=1568, media_max_bytes=1_500_000)`.

- [ ] **Step 1: Write failing test**

Create `test_runtime_tools.py`:

```python
from agentbox_api.runtime import build_registry
from agentbox_harness.spec import Mode


def test_registry_exposes_all_tools_with_flags():
    reg = build_registry(".")
    ask = Mode(name="ask", flags={"write": False})
    agent = Mode(name="agent", flags={"write": True})
    names_ask = {t.__name__ for t in reg.select_tools(ask)}
    names_agent = {t.__name__ for t in reg.select_tools(agent)}
    read = {
        "read_text_file", "read_file", "read_media_file", "read_multiple_files",
        "list_directory", "list_directory_with_sizes", "directory_tree",
        "search_files", "get_file_info", "list_allowed_directories",
    }
    write = {
        "write_file", "append_file", "edit_file", "create_directory",
        "move_file", "copy_file", "delete_path",
    }
    assert names_ask == read
    assert names_agent == read | write
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-api/tests/test_runtime_tools.py -q`
Expected: FAIL (only 3 tools registered).

- [ ] **Step 3: Implement**

In `config.py` add:

```python
    media_max_dimension: int = 1568
    media_max_bytes: int = 1_500_000
```

Replace `build_registry` with:

```python
def build_registry(
    project_root: str,
    extra_read_roots: list[pathlib.Path] | None = None,
    extra_tools: dict[str, Callable] | None = None,
    hooks: list | None = None,
    media_max_dimension: int = 1568,
    media_max_bytes: int = 1_500_000,
) -> ToolRegistry:
    box = FilesystemToolbox(
        pathlib.Path(project_root),
        extra_read_roots=list(extra_read_roots or []),
        media_max_dimension=media_max_dimension,
        media_max_bytes=media_max_bytes,
    )
    registry = ToolRegistry(hooks=hooks, root=box.root_dir)
    read_tools = [
        ("read_text_file", box.read_text_file),
        ("read_file", box.read_file),
        ("read_media_file", box.read_media_file),
        ("read_multiple_files", box.read_multiple_files),
        ("list_directory", box.list_directory),
        ("list_directory_with_sizes", box.list_directory_with_sizes),
        ("directory_tree", box.directory_tree),
        ("search_files", box.search_files),
        ("get_file_info", box.get_file_info),
        ("list_allowed_directories", box.list_allowed_directories),
    ]
    write_tools = [
        ("write_file", box.write_file),
        ("append_file", box.append_file),
        ("edit_file", box.edit_file),
        ("create_directory", box.create_directory),
        ("move_file", box.move_file),
        ("copy_file", box.copy_file),
        ("delete_path", box.delete_path),
    ]
    for name, fn in read_tools:
        registry.register_native(name, fn, required_flags=("read",))
    for name, fn in write_tools:
        registry.register_native(name, fn, required_flags=("write",))
    for name, fn in (extra_tools or {}).items():
        registry.register_native(name, fn)
    return registry
```

In `skills.py`, change the signature and `build_registry` call:

```python
async def prepare_agent(
    factory,
    agent_name: str,
    project_root: str,
    user_dir: str,
    media_max_dimension: int = 1568,
    media_max_bytes: int = 1_500_000,
) -> PreparedAgent:
    ...
    registry = build_registry(
        project_root,
        extra_read_roots=[s.location.parent for s in skills],
        extra_tools=extra_tools,
        media_max_dimension=media_max_dimension,
        media_max_bytes=media_max_bytes,
    )
```

Update the four call sites:

```python
# routers/sessions.py
    prepared = await prepare_agent(
        factory,
        agent.name,
        project.path,
        request.app.state.settings.skills_user_dir,
        media_max_dimension=request.app.state.settings.media_max_dimension,
        media_max_bytes=request.app.state.settings.media_max_bytes,
    )

# acp_server.py (both new_session and _restore)
        prepared = await prepare_agent(
            self._factory,
            self._agent_name,
            cwd,  # or project.path in _restore
            self._settings.skills_user_dir,
            media_max_dimension=self._settings.media_max_dimension,
            media_max_bytes=self._settings.media_max_bytes,
        )

# a2a_executor.py
        prepared = await prepare_agent(
            self._factory,
            self._agent_name,
            workspace,
            self._settings.skills_user_dir,
            media_max_dimension=self._settings.media_max_dimension,
            media_max_bytes=self._settings.media_max_bytes,
        )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest packages/agentbox-api/tests/test_runtime_tools.py packages/agentbox-api/tests/test_chat.py packages/agentbox-api/tests/test_skills.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-api/src/agentbox_api/runtime.py packages/agentbox-api/src/agentbox_api/config.py packages/agentbox-api/src/agentbox_api/skills.py packages/agentbox-api/src/agentbox_api/routers/sessions.py packages/agentbox-api/src/agentbox_api/acp_server.py packages/agentbox-api/src/agentbox_api/a2a_executor.py packages/agentbox-api/tests/test_runtime_tools.py
git commit -m "feat(api): register full filesystem toolset with media settings"
```

---

### Task 8: Agent UI lists every tool

**Files:**
- Modify: `apps/web/src/pages/AgentsPage.tsx:1` (the `NATIVE_TOOLS` constant)
- Test: `apps/web/src/pages/AgentsPage.test.tsx` (create)

**Interfaces:**
- Produces: `NATIVE_TOOLS` containing all 16 non-alias tools, rendered as unchecked checkboxes.

- [ ] **Step 1: Write failing test**

Create `apps/web/src/pages/AgentsPage.test.tsx`:

```tsx
import { NATIVE_TOOLS } from "./AgentsPage";

test("lists the full filesystem toolset", () => {
  expect(NATIVE_TOOLS).toContain("delete_path");
  expect(NATIVE_TOOLS).toContain("read_media_file");
  expect(NATIVE_TOOLS).toContain("directory_tree");
  expect(NATIVE_TOOLS).toHaveLength(16);
});
```

- [ ] **Step 2: Run and verify failure**

Run: `bun run test apps/web/src/pages/AgentsPage.test.tsx` (workdir `apps/web`)
Expected: FAIL (labels absent).

- [ ] **Step 3: Implement**

Replace the constant (and export it):

```tsx
export const NATIVE_TOOLS = [
  "read_text_file",
  "read_media_file",
  "read_multiple_files",
  "list_directory",
  "list_directory_with_sizes",
  "directory_tree",
  "search_files",
  "get_file_info",
  "list_allowed_directories",
  "write_file",
  "append_file",
  "edit_file",
  "create_directory",
  "move_file",
  "copy_file",
  "delete_path",
];
```

- [ ] **Step 4: Run test and build**

Run: `bun run test` then `bun run build` (workdir `apps/web`)
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/pages/AgentsPage.tsx apps/web/src/pages/AgentsPage.test.tsx
git commit -m "feat(web): expose full filesystem toolset in agent form"
```

---

### Task 9: Docs, roadmap, and full verification

**Files:**
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Update the roadmap**

Change the file-tools row to:

```markdown
| File tools (Codex / MCP FileSystem parity) | DONE | 17 native tools in `FilesystemToolbox` (read/write/tree/search/info/media/delete), guarded delete, post-tool hooks. |
```

Add sub-project #21:

```markdown
| 21 | Filesystem tools parity (reference toolset + media + hooks) | `specs/2026-11-19-filesystem-tools-design.md` | `plans/2026-11-19-filesystem-tools.md` |
```

- [ ] **Step 2: Run linters and full suites**

```bash
uv run ruff check --fix packages
uv run ty check packages
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-api -q
cd apps/web && bun run test && bun run build
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs(roadmap): filesystem toolset parity complete"
```
