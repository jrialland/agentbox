"""Detect language-server stacks and resolve their workspace roots.

Detection walks a project once, pruning dependency and build directories, and
matches marker globs against the remaining relative paths.
"""

import fnmatch
import os
import pathlib

from agentbox_harness.lsp.stacks import DEFAULT_LSP_SERVERS, LspStack

PRUNE_PARTS = {".git", ".venv", "node_modules", "target", "dist", "build", "__pycache__"}
MAX_WALK_ENTRIES = 100_000


def _matches(rel: str, marker: str) -> bool:
    tail = marker.removeprefix("**/")
    name = pathlib.PurePosixPath(rel).name
    return (
        fnmatch.fnmatch(rel, marker)
        or fnmatch.fnmatch(rel, tail)
        or fnmatch.fnmatch(name, tail)
    )


def _stack_matches(stack: LspStack, rels: list[str]) -> bool:
    return any(
        _matches(rel, marker) for marker in stack.markers for rel in rels
    )


def detect_stacks(
    project_root: str, stacks: list[LspStack] | tuple[LspStack, ...] | None = None
) -> list[LspStack]:
    """Return the stacks whose markers appear under a project root.

    The walk is synchronous and bounded by :data:`MAX_WALK_ENTRIES`; when the
    cap is hit detection stops early and returns matches from the files seen so
    far. Typical dependency, build, and hidden directories are pruned.

    Args:
        project_root: Project root to inspect.
        stacks: Candidate stacks; defaults to :data:`DEFAULT_LSP_SERVERS`.

    Returns:
        Candidate stacks that matched at least one marker, in input order.
    """
    root = pathlib.Path(project_root)
    candidates = DEFAULT_LSP_SERVERS if stacks is None else stacks
    rels: list[str] = []
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune in place so os.walk skips dependency, build, and hidden trees.
        dirnames[:] = [
            name
            for name in dirnames
            if name not in PRUNE_PARTS and not name.startswith(".")
        ]
        base = pathlib.Path(dirpath).relative_to(root).as_posix()
        for filename in filenames:
            count += 1
            if count > MAX_WALK_ENTRIES:
                # The entry cap bounds worst-case scans of large trees.
                return [stack for stack in candidates if _stack_matches(stack, rels)]
            rels.append(filename if base == "." else f"{base}/{filename}")
    return [stack for stack in candidates if _stack_matches(stack, rels)]


def nearest_root(stack: LspStack, path: str, fallback: str) -> pathlib.Path:
    """Find the nearest ancestor directory that looks like a stack root.

    Search climbs from the path's parent toward ``fallback``. Paths outside the
    fallback tree resolve to ``fallback`` immediately, so callers never escape
    the project root.

    Args:
        stack: Stack whose root markers define a workspace root.
        path: File path whose ancestors are searched.
        fallback: Project root returned when no marker matches.

    Returns:
        The nearest directory containing a root marker, or ``fallback``.
    """
    fallback_path = pathlib.Path(fallback).resolve()
    start = pathlib.Path(path).resolve().parent
    try:
        start.relative_to(fallback_path)
    except ValueError:
        # Do not climb above a caller-supplied project boundary.
        return fallback_path
    current = start
    markers = stack.root_markers or tuple(
        marker for marker in stack.markers if "*" not in marker and "/" not in marker
    )
    while True:
        if any((current / marker).is_file() for marker in markers):
            return current
        if current == fallback_path:
            return fallback_path
        current = current.parent
