"""Resolve project-relative paths and enforce allowed roots.

Used by terminal and MCP startup to keep a session inside its project root
and any explicitly configured extra roots.
"""

import pathlib


def resolve_project_path(
    value: str,
    project_root: str,
    extra_roots: list[str] | None = None,
) -> pathlib.Path:
    """Resolve a value to a path inside the project or an extra root.

    Relative values are resolved against ``project_root``; empty values return
    the project root itself. The resolved target must equal or live under one
    of the allowed roots.

    Args:
        value: Path to resolve, relative to the project root when not absolute.
        project_root: Project directory that anchors relative paths.
        extra_roots: Additional directories that are allowed targets.

    Returns:
        The resolved absolute path.

    Raises:
        ValueError: If the resolved path escapes the project and extra roots.
    """
    # Normalize every root once so containment checks compare fully resolved
    # paths instead of user-supplied strings.
    root = pathlib.Path(project_root).expanduser().resolve()
    allowed = list(
        dict.fromkeys(
            [
                root,
                *[pathlib.Path(path).expanduser().resolve() for path in extra_roots or []],
            ]
        )
    )
    # An empty or whitespace-only value means "the project root".
    if not value or not value.strip():
        return root
    candidate = pathlib.Path(value).expanduser()
    target = (candidate if candidate.is_absolute() else root / candidate).resolve()
    # Compare path components rather than string prefixes so sibling roots such
    # as /work and /work2 are not treated as contained.
    if not any(target == path or path in target.parents for path in allowed):
        raise ValueError(f"cwd escapes allowed roots: {value}")
    return target
