"""Filesystem tools for reading, writing, searching, and inspecting files.

Reads are restricted to the project and extra read roots, and writes to the
project and extra write roots. Blocking filesystem calls run in worker threads
with a timeout. Public methods are exposed to the model as tools.
"""

import asyncio
import fnmatch
import io
import mimetypes
import os
import pathlib
import shutil
import stat
from dataclasses import dataclass
from difflib import unified_diff

from loguru import logger
from PIL import Image
from pydantic_ai.messages import BinaryContent
from pydantic_ai.tools import ToolReturn

from agentbox_harness.tools.grep import (
    MAX_GREP_CONTEXT_LINES,
    GrepOptions,
    run_grep,
)

CALL_TIMEOUT_SECONDS = 15.0
MAX_WALK_ENTRIES = 100_000


class PathEscapesRootError(Exception):
    """Raised when a path resolves outside the toolbox's allowed roots."""


@dataclass(frozen=True)
class FileEdit:
    """A single old-text/new-text replacement applied by ``edit_file``."""

    old_text: str
    new_text: str


def _excluded(rel: str, name: str, patterns: list[str]) -> bool:
    """Return whether a path matches any exclude pattern."""
    for pattern in patterns:
        if "/" not in pattern and "*" not in pattern:
            if name == pattern:
                return True
            continue
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(name, pattern):
            return True
        if pattern.endswith("/**") and fnmatch.fnmatch(rel, pattern[:-3]):
            return True
    return False


def apply_file_edit(text: str, edit: FileEdit, newline: str) -> str:
    """Apply one edit, tolerating whitespace and newline differences.

    Falls back to a line-by-line match when the exact text is absent. On the
    fallback, new lines borrow the indentation of the line they replace.

    Args:
        text: Current file contents.
        edit: Replacement to apply.
        newline: Line ending used to rejoin the file.

    Returns:
        Updated file contents.

    Raises:
        ValueError: If ``old_text`` cannot be found.
    """
    if edit.old_text in text:
        return text.replace(edit.old_text, edit.new_text, 1)
    # Fallback: compare normalized lines with stripped indentation so edits
    # still apply when line endings or surrounding whitespace drifted.
    old_norm = edit.old_text.replace("\r\n", "\n").replace("\r", "\n")
    text_norm = text.replace("\r\n", "\n").replace("\r", "\n")
    old_lines = old_norm.split("\n")
    text_lines = text_norm.split("\n")
    count = len(old_lines)
    target = [line.strip() for line in old_lines]
    for index in range(len(text_lines) - count + 1):
        window = text_lines[index : index + count]
        if [line.strip() for line in window] == target:
            new_lines = (
                edit.new_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            )
            indented = []
            for offset, line in enumerate(new_lines):
                reference = window[min(offset, len(window) - 1)]
                indent = reference[: len(reference) - len(reference.lstrip())]
                indented.append(indent + line.lstrip() if line.strip() else line)
            return newline.join(
                text_lines[:index] + indented + text_lines[index + count :]
            )
    raise ValueError(f"old_text not found: {edit.old_text!r}")


class FilesystemToolbox:
    """Read, write, search, and inspect files under configured roots.

    Reads are limited to the project and extra read roots; writes are limited
    to the project and extra write roots. Public methods are exposed to the
    model as tools.
    """

    def __init__(
        self,
        root_dir: pathlib.Path,
        extra_read_roots: list[pathlib.Path] | None = None,
        extra_write_roots: list[pathlib.Path] | None = None,
        media_max_dimension: int = 1568,
        media_max_bytes: int = 1_500_000,
    ):
        self.root_dir = pathlib.Path(root_dir).resolve()
        write_roots = [
            pathlib.Path(root).resolve() for root in (extra_write_roots or [])
        ]
        read_roots = [
            pathlib.Path(root).resolve() for root in (extra_read_roots or [])
        ]
        self._write_roots = [self.root_dir, *write_roots]
        self._read_roots = list(
            dict.fromkeys([self.root_dir, *write_roots, *read_roots])
        )
        self.media_max_dimension = media_max_dimension
        self.media_max_bytes = media_max_bytes

    async def _blocking(self, fn, *args, **kwargs):
        """Run a blocking callable in a worker thread with a timeout."""
        return await asyncio.wait_for(
            asyncio.to_thread(fn, *args, **kwargs), CALL_TIMEOUT_SECONDS
        )

    async def _resolve(self, path: str, *, write: bool = False) -> pathlib.Path:
        """Resolve a user path and verify it stays inside an allowed root."""

        def _do() -> pathlib.Path:
            candidate = pathlib.Path(path)
            resolved = (
                candidate if candidate.is_absolute() else self.root_dir / candidate
            ).resolve()
            # Writes may only target write roots; reads may target the broader
            # read set that includes extra read-only roots.
            roots = self._write_roots if write else self._read_roots
            if not any(resolved == root or root in resolved.parents for root in roots):
                logger.warning(
                    "path escapes root path={} root={}", path, self.root_dir
                )
                raise PathEscapesRootError(path)
            return resolved

        return await self._blocking(_do)

    async def read_text_file(
        self, path: str, head: int | None = None, tail: int | None = None
    ) -> str:
        """Read a UTF-8 text file, optionally only the first or last lines.

        Args:
            path: File path relative to the project root.
            head: Return only the first this many lines.
            tail: Return only the last this many lines.

        Returns:
            File contents, or the requested slice, as text.

        Raises:
            ValueError: If both ``head`` and ``tail`` are given, or the path is
                not a regular file.
        """
        if head is not None and tail is not None:
            raise ValueError("head and tail are mutually exclusive")
        resolved = await self._resolve(path)
        if not stat.S_ISREG((await self._blocking(resolved.stat)).st_mode):
            raise ValueError(f"Not a regular file: {path}")
        text = await self._blocking(lambda: resolved.read_text(encoding="utf-8"))
        if head is not None:
            return "\n".join(text.splitlines()[:head])
        if tail is not None:
            return "\n".join(text.splitlines()[-tail:]) if tail else ""
        return text

    async def read_file(self, path: str) -> str:
        """Read an entire UTF-8 text file."""
        return await self.read_text_file(path)

    async def read_multiple_files(self, paths: list[str]) -> str:
        """Read several files, labeling each and reporting per-file errors.

        Args:
            paths: File paths relative to the project root.

        Returns:
            Concatenated ``--- path ---`` sections; unreadable files include an
            error message instead of raising.
        """
        parts = []
        for path in paths:
            try:
                parts.append(f"--- {path} ---\n{await self.read_text_file(path)}")
            except Exception as exc:
                parts.append(f"--- {path} ---\nError: {exc}")
        return "\n".join(parts)

    async def list_directory(self, path: str) -> str:
        """List immediate directory entries, marking each as a directory or file."""
        resolved = await self._resolve(path)
        entries = await self._blocking(
            lambda: sorted(resolved.iterdir(), key=lambda entry: entry.name)
        )
        return "\n".join(
            f"[{'DIR' if entry.is_dir() else 'FILE'}] {entry.name}"
            for entry in entries
        )

    async def list_directory_with_sizes(
        self, path: str, sort_by: str = "name"
    ) -> str:
        """List immediate entries with file sizes and a directory total.

        Args:
            path: Directory path relative to the project root.
            sort_by: ``size`` sorts largest first; any other value sorts by
                name.
        """
        resolved = await self._resolve(path)

        def _rows():
            rows = []
            for entry in resolved.iterdir():
                try:
                    size = entry.stat().st_size if entry.is_file() else 0
                except OSError:
                    size = None
                rows.append((entry.name, entry.is_dir(), size))
            if sort_by == "size":
                rows.sort(key=lambda row: (row[2] is None, -(row[2] or 0), row[0]))
            else:
                rows.sort(key=lambda row: row[0])
            return rows

        rows = await self._blocking(_rows)
        lines: list[str] = []
        files = dirs = total = 0
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
        """Return metadata for a path as a serializable dictionary."""
        resolved = await self._resolve(path)
        info = await self._blocking(resolved.stat)
        return {
            "path": str(resolved),
            "size": info.st_size,
            "created": info.st_ctime,
            "modified": info.st_mtime,
            "accessed": info.st_atime,
            "type": "directory" if resolved.is_dir() else "file",
            "permissions": stat.filemode(info.st_mode),
            "hardLinks": info.st_nlink,
        }

    async def directory_tree(
        self,
        path: str,
        exclude_patterns: list[str] | None = None,
        depth: int | None = None,
    ) -> list[dict]:
        """Build a nested tree of directory entries.

        Args:
            path: Directory path relative to the project root.
            exclude_patterns: Glob patterns to exclude.
            depth: Maximum directory depth to descend; ``None`` means
                unlimited.

        Returns:
            Nested nodes with ``name``, ``type``, and, for directories,
            ``children``.
        """
        resolved = await self._resolve(path)
        patterns = exclude_patterns or []
        counter = 0

        def build(dir_path: pathlib.Path, prefix: str, level: int) -> list[dict]:
            nonlocal counter
            nodes: list[dict] = []
            for entry in sorted(dir_path.iterdir(), key=lambda item: item.name):
                counter += 1
                if counter > MAX_WALK_ENTRIES:
                    raise ValueError(
                        f"stopped after visiting {MAX_WALK_ENTRIES} entries"
                    )
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

        return await self._blocking(build, resolved, "", 1)

    async def search_files(
        self,
        path: str,
        pattern: str,
        exclude_patterns: list[str] | None = None,
    ) -> str:
        """Find files whose path relative to the searched directory matches a glob.

        Args:
            path: Directory to search, relative to the project root.
            pattern: Glob pattern matched against each path relative to ``path``.
            exclude_patterns: Glob patterns to skip.

        Returns:
            Sorted absolute matching paths, plus a note when the walk was
            incomplete.
        """
        resolved = await self._resolve(path)
        patterns = exclude_patterns or []

        def walk():
            counter = 0
            matches: list[str] = []
            errors: list[str] = []

            def onerror(err):
                errors.append(f"{err.filename}: {err.strerror}")

            for dirpath, dirnames, filenames in os.walk(resolved, onerror=onerror):
                rel_dir = pathlib.Path(dirpath).relative_to(resolved).as_posix()
                kept = []
                for directory in dirnames:
                    rel = directory if rel_dir == "." else f"{rel_dir}/{directory}"
                    counter += 1
                    if counter > MAX_WALK_ENTRIES:
                        raise ValueError(
                            f"stopped after visiting {MAX_WALK_ENTRIES} entries"
                        )
                    if not _excluded(rel, directory, patterns):
                        kept.append(directory)
                dirnames[:] = kept
                for filename in filenames:
                    rel = filename if rel_dir == "." else f"{rel_dir}/{filename}"
                    counter += 1
                    if counter > MAX_WALK_ENTRIES:
                        raise ValueError(
                            f"stopped after visiting {MAX_WALK_ENTRIES} entries"
                        )
                    if _excluded(rel, filename, patterns):
                        continue
                    if fnmatch.fnmatch(rel, pattern):
                        matches.append(str(pathlib.Path(dirpath) / filename))
            return matches, errors

        matches, errors = await self._blocking(walk)
        output = "\n".join(sorted(matches))
        if errors:
            output += "\nNote: incomplete search:\n" + "\n".join(errors)
        return output

    async def grep(
        self,
        pattern: str,
        path: str = ".",
        fixed_strings: bool = False,
        ignore_case: bool = False,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        context_lines: int = 0,
    ) -> str:
        """Search file contents for a pattern.

        Use this for content searches; prefer ``search_files`` when you only
        need file names.

        Args:
            pattern: Regular expression, or literal text when ``fixed_strings``
                is set.
            path: File or directory to search, relative to the project root.
            fixed_strings: Treat the pattern as literal text.
            ignore_case: Match case-insensitively.
            include: Glob patterns limiting which files are searched.
            exclude: Glob patterns removing files from the search.
            context_lines: Lines of context to show around each match (0-3).

        Returns:
            Formatted matches with trailing notes for truncation or skipped
            files.
        """
        if not 0 <= context_lines <= MAX_GREP_CONTEXT_LINES:
            raise ValueError("context_lines must be between 0 and 3")
        resolved = await self._resolve(path)
        options = GrepOptions(
            pattern=pattern,
            root=resolved,
            project_root=self.root_dir,
            fixed_strings=fixed_strings,
            ignore_case=ignore_case,
            include=tuple(include or ()),
            exclude=tuple(exclude or ()),
            context_lines=context_lines,
        )
        return await self._blocking(run_grep, options)

    async def list_allowed_directories(self) -> str:
        """List the filesystem roots this session may read from."""
        return "\n".join(str(root) for root in self._read_roots)

    async def write_file(self, path: str, content: str) -> str:
        """Write text to a file, replacing any existing contents.

        The parent directory must already exist.

        Args:
            path: Target path relative to the project root.
            content: UTF-8 text to write.

        Returns:
            Confirmation with the number of characters written.
        """
        resolved = await self._resolve(path, write=True)
        if not resolved.parent.exists():
            raise ValueError(f"Parent directory does not exist: {resolved.parent}")
        await self._blocking(lambda: resolved.write_text(content, encoding="utf-8"))
        return f"Wrote {len(content)} bytes to {path}"

    async def append_file(self, path: str, content: str) -> str:
        """Append text to a file, creating it when needed.

        Returns:
            Confirmation with the number of characters appended.
        """
        resolved = await self._resolve(path, write=True)
        if not resolved.parent.exists():
            raise ValueError(f"Parent directory does not exist: {resolved.parent}")
        with resolved.open("a", encoding="utf-8") as handle:
            handle.write(content)
        return f"Appended {len(content)} bytes to {path}"

    async def create_directory(self, path: str) -> str:
        """Create a directory and any missing parents."""
        resolved = await self._resolve(path, write=True)
        await self._blocking(lambda: resolved.mkdir(parents=True, exist_ok=True))
        return f"Created directory {path}"

    async def move_file(self, source: str, destination: str) -> str:
        """Move or rename a file or directory within the writable roots."""
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
        """Copy a file to a new path without overwriting an existing file."""
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
        """Delete a file, symlink, or directory.

        Args:
            path: Target path relative to the project root.
            recursive: Remove a non-empty directory and its contents.

        Returns:
            Confirmation that the path was deleted.

        Raises:
            ValueError: If the path is an allowed root or a non-empty directory
                is deleted without ``recursive``.
        """
        candidate = pathlib.Path(path)
        target = candidate if candidate.is_absolute() else self.root_dir / candidate
        target_resolved = target.resolve()
        # Never allow a delete to remove a configured root wholesale.
        if any(target_resolved == root for root in self._write_roots):
            raise ValueError("Refusing to delete an allowed root")
        parent = target.parent.resolve()
        if not any(
            parent == root or root in parent.parents for root in self._write_roots
        ):
            raise PathEscapesRootError(path)

        def _delete() -> None:
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

    async def edit_file(
        self,
        path: str,
        edits: list[FileEdit],
        dry_run: bool = False,
    ) -> str:
        """Apply exact-text edits to a file.

        Each edit replaces the first matching text. When the exact text is
        absent, a whitespace-tolerant line match is used.

        Args:
            path: File path relative to the project root.
            edits: Ordered replacements to apply.
            dry_run: Return a unified diff instead of writing the file.

        Returns:
            ``Edited <path>`` after writing, a diff for a dry run, or
            ``No changes``.
        """
        resolved = await self._resolve(path, write=True)
        raw = (await self._blocking(lambda: resolved.read_bytes())).decode("utf-8")
        # Preserve the file's existing line endings when rejoining edited lines.
        newline = "\r\n" if "\r\n" in raw else ("\r" if "\r" in raw else "\n")
        updated = raw
        for edit in edits:
            updated = apply_file_edit(updated, edit, newline)
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
            lambda: resolved.write_bytes(updated.encode("utf-8"))
        )
        return f"Edited {path}"

    def _optimize_image(self, data: bytes) -> tuple[bytes, int, int]:
        """Downscale and re-encode an image to fit the media size limits."""
        with Image.open(io.BytesIO(data)) as image:
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert(
                    "RGBA" if "A" in image.getbands() else "RGB"
                )
            if max(image.size) > self.media_max_dimension:
                image.thumbnail(
                    (self.media_max_dimension, self.media_max_dimension),
                    Image.Resampling.LANCZOS,
                )
            while True:
                buffer = io.BytesIO()
                image.save(buffer, format="PNG", optimize=True)
                output = buffer.getvalue()
                if len(output) <= self.media_max_bytes or max(image.size) <= 32:
                    return output, image.width, image.height
                image = image.resize(
                    (
                        max(1, int(image.width * 0.8)),
                        max(1, int(image.height * 0.8)),
                    ),
                    Image.Resampling.LANCZOS,
                )

    async def read_media_file(self, path: str) -> ToolReturn:
        """Read a media file and return it as model content.

        Images are re-encoded to PNG and downscaled to fit the configured
        limits; other files are returned with their detected media type.

        Args:
            path: Media path relative to the project root.

        Returns:
            A tool return with a short summary and the binary content.
        """
        resolved = await self._resolve(path)
        if not resolved.is_file():
            raise ValueError(f"Not a regular file: {path}")
        data = await self._blocking(lambda: resolved.read_bytes())
        media_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        if media_type.startswith("image/"):
            try:
                png, width, height = await self._blocking(
                    self._optimize_image, data
                )
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
