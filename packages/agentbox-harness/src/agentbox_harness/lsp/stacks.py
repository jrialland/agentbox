import pathlib
from dataclasses import dataclass


@dataclass(frozen=True)
class LspStack:
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
    extension = pathlib.Path(path).suffix.lower()
    if extension not in stack.extensions:
        return None
    language = LANGUAGE_BY_EXTENSION.get(extension)
    return language if language in stack.languages else None


def stack_for_path(stacks, path: str) -> LspStack | None:
    for stack in stacks:
        if language_for(stack, path):
            return stack
    return None
