import pathlib
from dataclasses import dataclass


@dataclass(frozen=True)
class LspStack:
    name: str
    markers: tuple[str, ...]
    command: tuple[str, ...]
    languages: tuple[str, ...]
    extensions: tuple[str, ...]


DEFAULT_LSP_SERVERS = (
    LspStack(
        name="python",
        markers=("pyproject.toml", "setup.py", "requirements.txt", "**/*.py"),
        command=("uvx", "ty", "server"),
        languages=("python",),
        extensions=(".py", ".pyi"),
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
    ),
    LspStack(
        name="rust",
        markers=("**/Cargo.toml",),
        command=("rust-analyzer",),
        languages=("rust",),
        extensions=(".rs",),
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
