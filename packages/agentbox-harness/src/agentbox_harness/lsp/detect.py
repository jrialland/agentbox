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
    root = pathlib.Path(project_root)
    candidates = DEFAULT_LSP_SERVERS if stacks is None else stacks
    rels: list[str] = []
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in PRUNE_PARTS and not name.startswith(".")
        ]
        base = pathlib.Path(dirpath).relative_to(root).as_posix()
        for filename in filenames:
            count += 1
            if count > MAX_WALK_ENTRIES:
                return [stack for stack in candidates if _stack_matches(stack, rels)]
            rels.append(filename if base == "." else f"{base}/{filename}")
    return [stack for stack in candidates if _stack_matches(stack, rels)]


def nearest_root(stack: LspStack, path: str, fallback: str) -> pathlib.Path:
    fallback_path = pathlib.Path(fallback).resolve()
    start = pathlib.Path(path).resolve().parent
    try:
        start.relative_to(fallback_path)
    except ValueError:
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
