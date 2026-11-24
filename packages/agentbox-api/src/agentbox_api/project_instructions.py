"""Discover and inject ``AGENTS.md`` project instructions.

Instructions come from a user-global file, the project root, and nested
directories touched by tools. Reads are confined to their boundary, truncated to
a shared byte budget, cached across reads, and delivered once per session through
a tool hook. All state is process-local.
"""

from __future__ import annotations

import hashlib
import pathlib
from dataclasses import dataclass, field

from loguru import logger

from agentbox_harness.tools.registry import ToolHookContext

MAX_INSTRUCTION_BYTES = 32 * 1024
AGENTS_FILENAME = "AGENTS.md"

_content_cache: dict[pathlib.Path, str] = {}


@dataclass(frozen=True)
class InstructionFile:
    """A loaded instruction file with its display source and scope."""

    path: pathlib.Path
    source: str
    scope: str
    content: str
    truncated: bool = False


def global_instructions_path() -> pathlib.Path:
    """Return the user-global ``AGENTS.md`` path in the home directory."""
    return pathlib.Path.home() / AGENTS_FILENAME


def _truncate_utf8(text: str, limit: int) -> tuple[str, bool]:
    # Drop bytes from the end until the cut decodes, so multibyte characters are
    # never split mid-sequence.
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
    """Read and truncate an instruction file if it stays within ``boundary``.

    Args:
        path: Candidate instruction file.
        boundary: Directory the resolved path must stay inside.
        source: Display label recorded on the resulting file.
        scope: Scope label (``global``, ``project``, or ``nested``).
        max_bytes: Maximum UTF-8 bytes to include.

    Returns:
        The instruction file, or ``None`` when missing, empty, unreadable, or
        outside the boundary.
    """
    try:
        resolved = path.expanduser().resolve()
        boundary_resolved = boundary.expanduser().resolve()
    except OSError as exc:
        logger.warning("instruction path resolve failed path={} error={}", path, exc)
        return None
    # Confine reads to the boundary so a symlink or ``..`` cannot pull in
    # instructions from outside the project or home directory.
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
        # Fall back to the last good content when a transient read fails.
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
    """Load the user-global ``~/AGENTS.md`` instructions."""
    path = global_instructions_path()
    return read_instruction_file(
        path,
        boundary=path.parent,
        source="~/AGENTS.md",
        scope="global",
        max_bytes=MAX_INSTRUCTION_BYTES,
    )


def load_project_instructions(project_root: str) -> InstructionFile | None:
    """Load the project-root ``AGENTS.md`` instructions.

    Args:
        project_root: Project root containing ``AGENTS.md``.
    """
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
    """Load a nested ``AGENTS.md`` relative to a project root.

    Args:
        project_root: Project root used as the containment boundary.
        path: Nested instruction file to load.

    Returns:
        The instruction file, or ``None`` when it is outside the project.
    """
    root = pathlib.Path(project_root).expanduser().resolve()
    try:
        # A relative source doubles as the containment check for nested files.
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
    """Per-session accounting of delivered instruction content.

    Tracks content hashes and byte usage so the shared budget is respected and
    unchanged nested instructions are not re-delivered.
    """

    root_hash: str | None = None
    global_hash: str | None = None
    root_bytes: int = 0
    nested_bytes: int = 0
    delivered: dict[pathlib.Path, str] = field(default_factory=dict)


_states: dict[str, InstructionState] = {}


def get_instruction_state(session_id: str | None) -> InstructionState:
    """Return the state for a session, or a fresh one when id is ``None``.

    Args:
        session_id: Session to look up.

    Returns:
        The session's persistent state, or an unregistered throwaway state when
        no session id is supplied.
    """
    if session_id is None:
        return InstructionState()
    return _states.setdefault(session_id, InstructionState())


def clear_instruction_state(session_id: str) -> None:
    """Drop the cached instruction state for a session.

    Args:
        session_id: Session whose state should be forgotten.
    """
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
    """Build the system-prompt block for global and project-root instructions.

    The global file is inserted first (lowest precedence in the prompt) and the
    project-root file after it; nested instructions are appended later by the
    tool hook. All sources share one byte budget.

    Args:
        project_root: Project root whose ``AGENTS.md`` applies.
        session_id: Session used to track delivered content; ``None`` disables
            persistence of that state.

    Returns:
        The formatted instruction block, or an empty string when none apply.
    """
    state = get_instruction_state(session_id)
    root = load_project_instructions(project_root)
    global_file = load_global_instructions()
    blocks: list[str] = []

    # Root instructions claim their bytes first; nested content is reserved from
    # the existing state so the global file cannot crowd it out.
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

NESTED_TOOLS = {
    "read_text_file",
    "read_file",
    "read_multiple_files",
    "list_directory",
    "list_directory_with_sizes",
    "search_files",
    "write_file",
    "append_file",
    "edit_file",
    "create_directory",
    "move_file",
    "copy_file",
    "delete_path",
}


def _target_paths(tool_name: str, args: dict) -> list[str]:
    if "paths" in args and isinstance(args["paths"], list):
        return [str(value) for value in args["paths"]]
    if tool_name in {"move_file", "copy_file"}:
        return [
            str(value)
            for value in (args.get("source"), args.get("destination"))
            if value
        ]
    path = args.get("path")
    return [str(path)] if path else []


def discover_nested_agents(project_root: str, target: str) -> list[pathlib.Path]:
    """Find ``AGENTS.md`` files between the project root and a target path.

    Args:
        project_root: Project root that bounds the search.
        target: File or directory path to walk up from.

    Returns:
        Existing instruction paths ordered outermost-first, so more specific
        nested instructions come later. Empty when the target is outside the
        project.
    """
    root = pathlib.Path(project_root).expanduser().resolve()
    candidate = pathlib.Path(target).expanduser()
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    # Refuse to walk outside the project root.
    if not _inside(resolved, root):
        return []
    current = resolved if resolved.is_dir() else resolved.parent
    found: list[pathlib.Path] = []
    # Collect from the target upward, then reverse so ancestors come first.
    while current != root and root in current.parents:
        agents = current / AGENTS_FILENAME
        if agents.is_file():
            found.append(agents)
        current = current.parent
    return list(reversed(found))


def make_project_instructions_hook(project_root: str, session_id: str):
    """Build a tool hook that appends newly relevant nested instructions.

    The hook inspects filesystem tool calls, discovers ``AGENTS.md`` files
    between the project root and each touched path, and appends content that has
    not already been delivered to the session. Paths outside the project are
    ignored.

    Args:
        project_root: Project root used as the containment boundary.
        session_id: Session whose delivered-state tracks what was sent.

    Returns:
        An async tool hook returning extra instruction blocks or ``None``.
    """

    async def hook(ctx: ToolHookContext) -> str | None:
        if ctx.tool_name not in NESTED_TOOLS or not isinstance(ctx.result, str):
            return None
        state = get_instruction_state(session_id)
        root = pathlib.Path(project_root).expanduser().resolve()
        targets = _target_paths(ctx.tool_name, ctx.args)
        blocks: list[str] = []
        seen: set[pathlib.Path] = set()
        ancestor_dirs: set[pathlib.Path] = set()

        for target in targets:
            candidate = pathlib.Path(target).expanduser()
            resolved = (
                candidate if candidate.is_absolute() else root / candidate
            ).resolve()
            # Ignore targets outside the project; their instructions do not
            # apply and must not be read.
            if not _inside(resolved, root):
                continue
            current = resolved if resolved.is_dir() else resolved.parent
            while current != root and root in current.parents:
                ancestor_dirs.add(current)
                current = current.parent
            for path in discover_nested_agents(project_root, target):
                if path in seen:
                    continue
                seen.add(path)
                loaded = load_nested_instructions(project_root, path)
                if loaded is None:
                    continue
                digest = _digest(loaded.content)
                # Skip content already sent to this session unchanged.
                if state.delivered.get(path) == digest:
                    continue
                # Nested instructions share the budget left after root content
                # and everything already delivered.
                remaining = max(
                    MAX_INSTRUCTION_BYTES - state.root_bytes - state.nested_bytes,
                    0,
                )
                content, truncated = _truncate_utf8(loaded.content, remaining)
                if not content.strip():
                    blocks.append(
                        f'<project_instructions source="{loaded.source}" '
                        'scope="nested">Nested instructions omitted: shared '
                        "32 KiB budget exhausted.</project_instructions>"
                    )
                    continue
                state.delivered[path] = digest
                state.nested_bytes += len(content.encode("utf-8"))
                blocks.append(_block(loaded, content, truncated or loaded.truncated))

        # Withdraw instructions that were delivered but have since been deleted
        # along a path we touched, releasing their budget.
        for path in list(state.delivered):
            if path.parent in ancestor_dirs and not path.is_file():
                blocks.append(
                    f'<project_instructions source="{path.relative_to(root).as_posix()}" '
                    'scope="nested">This nested AGENTS.md no longer applies.'
                    "</project_instructions>"
                )
                state.nested_bytes = max(
                    0,
                    state.nested_bytes
                    - len(_content_cache.get(path, "").encode("utf-8")),
                )
                state.delivered.pop(path, None)
        return "\n\n".join(blocks) or None

    return hook
