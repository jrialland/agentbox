from __future__ import annotations

import hashlib
import pathlib
from dataclasses import dataclass, field

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


@dataclass
class InstructionState:
    root_hash: str | None = None
    global_hash: str | None = None
    root_bytes: int = 0
    nested_bytes: int = 0
    delivered: dict[pathlib.Path, str] = field(default_factory=dict)


_states: dict[str, InstructionState] = {}


def get_instruction_state(session_id: str | None) -> InstructionState:
    if session_id is None:
        return InstructionState()
    return _states.setdefault(session_id, InstructionState())


def clear_instruction_state(session_id: str) -> None:
    _states.pop(session_id, None)


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _block(file: InstructionFile, content: str, truncated: bool) -> str:
    suffix = (
        "\n\n[Truncated to fit the shared 32 KiB instruction budget.]"
        if truncated
        else ""
    )
    return (
        f'<project_instructions source="{file.source}" scope="{file.scope}">\n'
        f"{content.strip()}{suffix}\n</project_instructions>"
    )


def build_system_instruction_block(project_root: str, session_id: str | None) -> str:
    state = get_instruction_state(session_id)
    root = load_project_instructions(project_root)
    global_file = load_global_instructions()
    blocks: list[str] = []

    root_content = root.content if root else ""
    root_bytes = len(root_content.encode("utf-8"))
    state.root_bytes = root_bytes
    state.root_hash = _digest(root_content) if root else None
    if root:
        blocks.append(_block(root, root_content, root.truncated))

    nested_reserved = min(state.nested_bytes, MAX_INSTRUCTION_BYTES)
    remaining = max(MAX_INSTRUCTION_BYTES - root_bytes - nested_reserved, 0)
    if global_file:
        global_content, global_truncated = _truncate_utf8(global_file.content, remaining)
        state.global_hash = _digest(global_file.content)
        if global_content.strip():
            blocks.insert(
                0,
                _block(global_file, global_content, global_truncated or global_file.truncated),
            )
        else:
            blocks.insert(
                0,
                '<project_instructions source="~/AGENTS.md" scope="global">'
                "Global instructions omitted: shared 32 KiB budget exhausted."
                "</project_instructions>",
            )
    else:
        state.global_hash = None

    if not blocks:
        return ""
    return (
        "Project instructions follow. Explicit user messages override them.\n\n"
        + "\n\n".join(blocks)
    )