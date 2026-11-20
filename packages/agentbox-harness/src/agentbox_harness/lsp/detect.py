import pathlib

from agentbox_harness.lsp.stacks import DEFAULT_LSP_SERVERS, LspStack

PRUNE_PARTS = {".git", ".venv", "node_modules", "target", "dist", "build", "__pycache__"}


def _kept(path: pathlib.Path, root: pathlib.Path) -> bool:
    return not any(
        part in PRUNE_PARTS or part.startswith(".")
        for part in path.relative_to(root).parts[:-1]
    )


def detect_stacks(
    project_root: str, stacks: list[LspStack] | tuple[LspStack, ...] | None = None
) -> list[LspStack]:
    root = pathlib.Path(project_root)
    found: list[LspStack] = []
    for stack in DEFAULT_LSP_SERVERS if stacks is None else stacks:
        for marker in stack.markers:
            matches = [path for path in root.glob(marker) if _kept(path, root)]
            if matches:
                found.append(stack)
                break
    return found
