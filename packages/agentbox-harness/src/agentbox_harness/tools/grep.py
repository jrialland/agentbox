"""Grep implementation shared by the filesystem and grep tools.

Walks a root without following symlinks, skips common build and version-control
directories, and guards each file with byte-size and binary checks before
matching.
"""

from __future__ import annotations

import fnmatch
import os
import pathlib
import re
from dataclasses import dataclass

MAX_GREP_RESULTS = 200
MAX_GREP_LINE_CHARS = 300
MAX_GREP_FILE_BYTES = 2 * 1024 * 1024
MAX_GREP_WALK_ENTRIES = 100_000
MAX_GREP_CONTEXT_LINES = 3
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
}


@dataclass(frozen=True)
class GrepOptions:
    """Inputs for :func:`run_grep`, including match, filter, and size limits.

    ``project_root`` is used only to render shorter display paths for matches
    inside the project.
    """

    pattern: str
    root: pathlib.Path
    project_root: pathlib.Path
    fixed_strings: bool = False
    ignore_case: bool = False
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    context_lines: int = 0
    max_results: int = MAX_GREP_RESULTS
    max_file_bytes: int = MAX_GREP_FILE_BYTES
    max_line_chars: int = MAX_GREP_LINE_CHARS
    max_walk_entries: int = MAX_GREP_WALK_ENTRIES


def _clip(text: str, limit: int) -> str:
    """Shorten a line to ``limit`` characters, adding an ellipsis."""
    return text if len(text) <= limit else text[: max(limit - 1, 0)] + "…"


def _display_path(path: pathlib.Path, project_root: pathlib.Path) -> str:
    """Return a path relative to the project root when possible."""
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _matches(rel: str, name: str, patterns: tuple[str, ...]) -> bool:
    """Return whether a relative path or file name matches any glob pattern."""
    return any(
        fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(name, pattern)
        for pattern in patterns
    )


def _selected(path: pathlib.Path, root: pathlib.Path, options: GrepOptions) -> bool:
    """Apply include and exclude patterns to a candidate file."""
    rel = path.relative_to(root).as_posix()
    if options.include and not _matches(rel, path.name, options.include):
        return False
    return not _matches(rel, path.name, options.exclude)


def _iter_files(options: GrepOptions) -> tuple[list[pathlib.Path], bool]:
    """Collect candidate files under the root and report walk truncation."""
    if options.root.is_file():
        return [options.root], False
    files: list[pathlib.Path] = []
    visited = 0
    for dirpath, dirnames, filenames in os.walk(
        options.root, followlinks=False
    ):
        # Prune excluded directories before descending to avoid walking
        # dependency and build trees.
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name not in DEFAULT_EXCLUDED_DIRS
            and not _matches(
                pathlib.Path(dirpath, name)
                .relative_to(options.root)
                .as_posix(),
                name,
                options.exclude,
            )
        )
        for name in sorted(filenames):
            visited += 1
            if visited > options.max_walk_entries:
                return files, True
            path = pathlib.Path(dirpath, name)
            if path.is_symlink():
                continue
            if _selected(path, options.root, options):
                files.append(path)
    return files, False


def _read_lines(
    path: pathlib.Path, options: GrepOptions
) -> list[str] | None:
    """Read a file as lines, or return ``None`` for large, binary, or unreadable files."""
    try:
        if path.stat().st_size > options.max_file_bytes:
            return None
        with path.open("rb") as handle:
            # A NUL byte in the first chunk is treated as a binary-file signal.
            head = handle.read(8192)
            if b"\x00" in head:
                return None
            data = head + handle.read()
        return data.decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None


def run_grep(options: GrepOptions) -> str:
    """Search files under a root and return formatted match lines.

    Matches are emitted as ``path:line:column:text`` and context lines as
    ``path-line-text``. Truncation, skipped files, and empty results are
    reported as trailing notes instead of raising.

    Args:
        options: Pattern, root, filters, and limits for the search.

    Returns:
        Newline-joined matches with explanatory notes, or ``No matches.``.

    Raises:
        ValueError: If the pattern is empty, the regex is invalid, or context
            lines exceed the supported maximum.
    """
    if not options.pattern.strip():
        raise ValueError("pattern must not be empty")
    if not 0 <= options.context_lines <= MAX_GREP_CONTEXT_LINES:
        raise ValueError("context_lines must be between 0 and 3")
    flags = re.IGNORECASE if options.ignore_case else 0
    source = re.escape(options.pattern) if options.fixed_strings else options.pattern
    try:
        regex = re.compile(source, flags)
    except re.error as exc:
        raise ValueError(f"Invalid regex: {exc}") from exc

    files, walk_truncated = _iter_files(options)
    matched = 0
    skipped = 0
    truncated = False
    output: list[str] = []

    for path in files:
        lines = _read_lines(path, options)
        if lines is None:
            skipped += 1
            continue
        display_path = _display_path(path, options.project_root)
        selected: dict[int, tuple[int, str] | None] = {}
        for number, line in enumerate(lines, start=1):
            if matched >= options.max_results:
                truncated = True
                break
            match = regex.search(line)
            if match is None:
                continue
            matched += 1
            selected[number] = (match.start() + 1, line)
            for context_number in range(
                max(1, number - options.context_lines),
                min(len(lines), number + options.context_lines) + 1,
            ):
                selected.setdefault(context_number, None)
        if not selected:
            continue
        for number in sorted(selected):
            value = selected[number]
            if value is None:
                output.append(
                    f"{display_path}-{number}-"
                    f"{_clip(lines[number - 1], options.max_line_chars)}"
                )
            else:
                column, line = value
                output.append(
                    f"{display_path}:{number}:{column}:"
                    f"{_clip(line, options.max_line_chars)}"
                )
        if truncated:
            break

    if not output:
        output.append("No matches.")
    if truncated:
        output.append(
            f"Stopped after {options.max_results} matches; "
            "narrow the path or pattern."
        )
    if walk_truncated:
        output.append("Search truncated after the walk-entry limit.")
    if skipped:
        output.append(f"Skipped {skipped} binary, large, or unreadable files.")
    return "\n".join(output)
