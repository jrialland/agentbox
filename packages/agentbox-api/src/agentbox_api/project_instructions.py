from __future__ import annotations

import pathlib
from dataclasses import dataclass

from loguru import logger

MAX_INSTRUCTION_BYTES = 32 * 1024
AGENTS_FILENAME = "AGENTS.md"

_content_cache: dict[pathlib.Path, str] = {}


@dataclass(frozen=True)
class InstructionFile:
    path: pathlib.Path
    source: str
    scope: str
    content: str
    truncated: bool = False


def global_instructions_path() -> pathlib.Path:
    return pathlib.Path.home() / AGENTS_FILENAME


def _truncate_utf8(text: str, limit: int) -> tuple[str, bool]:
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text, False
    cut = data[:limit]
    while cut:
        try:
            return cut.decode("utf-8"), True
        except UnicodeDecodeError:
            cut = cut[:-1]
    return "", True


def _inside(path: pathlib.Path, boundary: pathlib.Path) -> bool:
    return path == boundary or boundary in path.parents


def read_instruction_file(
    path: pathlib.Path,
    *,
    boundary: pathlib.Path,
    source: str,
    scope: str,
    max_bytes: int,
) -> InstructionFile | None:
    try:
        resolved = path.expanduser().resolve()
        boundary_resolved = boundary.expanduser().resolve()
    except OSError as exc:
        logger.warning("instruction path resolve failed path={} error={}", path, exc)
        return None
    if not _inside(resolved, boundary_resolved):
        logger.warning(
            "instruction path escapes boundary path={} boundary={}",
            resolved,
            boundary_resolved,
        )
        return None
    try:
        raw = resolved.read_bytes()
    except FileNotFoundError:
        _content_cache.pop(resolved, None)
        return None
    except OSError as exc:
        cached = _content_cache.get(resolved)
        if cached is None:
            logger.warning("instruction read failed path={} error={}", resolved, exc)
            return None
        logger.warning(
            "instruction read failed; using cached content path={} error={}",
            resolved,
            exc,
        )
        text = cached
    else:
        text = raw.decode("utf-8", errors="replace")
        if not text.strip():
            _content_cache.pop(resolved, None)
            return None
        _content_cache[resolved] = text
    content, truncated = _truncate_utf8(text, max_bytes)
    if not content.strip():
        return None
    return InstructionFile(
        path=resolved,
        source=source,
        scope=scope,
        content=content,
        truncated=truncated,
    )


def load_global_instructions() -> InstructionFile | None:
    path = global_instructions_path()
    return read_instruction_file(
        path,
        boundary=path.parent,
        source="~/AGENTS.md",
        scope="global",
        max_bytes=MAX_INSTRUCTION_BYTES,
    )


def load_project_instructions(project_root: str) -> InstructionFile | None:
    root = pathlib.Path(project_root).expanduser().resolve()
    return read_instruction_file(
        root / AGENTS_FILENAME,
        boundary=root,
        source=AGENTS_FILENAME,
        scope="project",
        max_bytes=MAX_INSTRUCTION_BYTES,
    )


def load_nested_instructions(
    project_root: str, path: pathlib.Path
) -> InstructionFile | None:
    root = pathlib.Path(project_root).expanduser().resolve()
    try:
        source = path.resolve().relative_to(root).as_posix()
    except ValueError:
        return None
    return read_instruction_file(
        path,
        boundary=root,
        source=source,
        scope="nested",
        max_bytes=MAX_INSTRUCTION_BYTES,
    )
