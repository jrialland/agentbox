import pathlib


def resolve_project_path(
    value: str,
    project_root: str,
    extra_roots: list[str] | None = None,
) -> pathlib.Path:
    root = pathlib.Path(project_root).expanduser().resolve()
    allowed = list(
        dict.fromkeys(
            [
                root,
                *[pathlib.Path(path).expanduser().resolve() for path in extra_roots or []],
            ]
        )
    )
    if not value or not value.strip():
        return root
    candidate = pathlib.Path(value).expanduser()
    target = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if not any(target == path or path in target.parents for path in allowed):
        raise ValueError(f"cwd escapes allowed roots: {value}")
    return target
