"""Language-server stack definitions and path-to-language mapping.

A :class:`LspStack` describes one language server: the project markers that
detect it, the command that starts it, and the file extensions it handles.
"""

import pathlib
from dataclasses import dataclass


@dataclass(frozen=True)
class LspStack:
    """Configuration for one language server and the files it analyzes.

    Attributes:
        name: Stable stack name used as a manager key and in health output.
        markers: Project-relative glob patterns that signal this stack.
        command: Executable and arguments used to spawn the server.
        languages: LSP ``languageId`` values this stack accepts.
        extensions: File extensions routed to this stack.
        root_markers: Files that mark the workspace root; empty means derive
            roots from the non-glob ``markers``.
        pull: Whether to request diagnostics with pull requests instead of
            relying only on published notifications.
        save: Whether document sync sends an explicit ``didSave`` notification.
        settle: Debounce window, in seconds, after edit-driven diagnostics.
        quiescence: Optional server-status strategy; ``"server_status"`` enables
            the experimental quiescence tracker.
        first_change_timeout: Seconds to wait for the first diagnostic change.
        settle_window: Seconds of silence required before results are stable.
        post_quiescence_grace: Extra seconds to collect results after quiescence.
    """

    name: str
    markers: tuple[str, ...]
    command: tuple[str, ...]
    languages: tuple[str, ...]
    extensions: tuple[str, ...]
    root_markers: tuple[str, ...] = ()
    pull: bool = True
    save: bool = False
    settle: float = 3.0
    quiescence: str | None = None
    first_change_timeout: float = 1.0
    settle_window: float = 0.3
    post_quiescence_grace: float = 0.5


DEFAULT_LSP_SERVERS = (
    LspStack(
        name="python",
        markers=("pyproject.toml", "setup.py", "requirements.txt", "**/*.py"),
        command=("uvx", "ty", "server"),
        languages=("python",),
        extensions=(".py", ".pyi"),
        root_markers=(
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "requirements.txt",
            "Pipfile",
            "pyrightconfig.json",
        ),
    ),
    LspStack(
        name="typescript",
        markers=("**/tsconfig.json", "**/package.json"),
        command=(
            "npx",
            "-y",
            "typescript-language-server@latest",
            "--stdio",
        ),
        languages=("typescript", "typescriptreact", "javascript", "javascriptreact"),
        extensions=(".ts", ".tsx", ".js", ".jsx"),
        root_markers=(
            "package-lock.json",
            "bun.lockb",
            "bun.lock",
            "pnpm-lock.yaml",
            "yarn.lock",
            "tsconfig.json",
            "package.json",
        ),
    ),
    LspStack(
        name="rust",
        markers=("**/Cargo.toml",),
        command=("rust-analyzer",),
        languages=("rust",),
        extensions=(".rs",),
        root_markers=("Cargo.toml",),
        pull=False,
        save=True,
        settle=15.0,
        quiescence="server_status",
        first_change_timeout=1.0,
        settle_window=0.3,
        post_quiescence_grace=0.5,
    ),
)

LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".rs": "rust",
}


def language_for(stack: LspStack, path: str) -> str | None:
    """Return the LSP language id for a path, or ``None`` when unsupported.

    Args:
        stack: Stack whose extensions and languages gate the result.
        path: File path whose suffix selects the language.

    Returns:
        The language id when both the extension and language belong to the
        stack, otherwise ``None``.
    """
    extension = pathlib.Path(path).suffix.lower()
    if extension not in stack.extensions:
        return None
    language = LANGUAGE_BY_EXTENSION.get(extension)
    return language if language in stack.languages else None


def stack_for_path(stacks, path: str) -> LspStack | None:
    """Return the first stack that supports a path, or ``None``.

    Args:
        stacks: Ordered stacks to test; earlier entries win.
        path: File path to match against each stack's extensions.

    Returns:
        The first matching :class:`LspStack`, or ``None`` when unsupported.
    """
    for stack in stacks:
        if language_for(stack, path):
            return stack
    return None
