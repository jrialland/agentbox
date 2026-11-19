import pathlib
import shutil
from dataclasses import dataclass

from loguru import logger


class PathEscapesRootError(Exception):
    pass


@dataclass(frozen=True)
class FileEdit:
    old_text: str
    new_text: str


class FilesystemToolbox:
    def __init__(
        self, root_dir: pathlib.Path, extra_read_roots: list[pathlib.Path] | None = None
    ):
        self.root_dir = pathlib.Path(root_dir).resolve()
        self._read_roots = [
            self.root_dir,
            *[pathlib.Path(r).resolve() for r in (extra_read_roots or [])],
        ]

    def _resolve(self, path: str, *, write: bool = False) -> pathlib.Path:
        candidate = pathlib.Path(path)
        p = (
            candidate if candidate.is_absolute() else self.root_dir / candidate
        ).resolve()
        roots = [self.root_dir] if write else self._read_roots
        if not any(p == r or r in p.parents for r in roots):
            logger.warning("path escapes root path={} root={}", path, self.root_dir)
            raise PathEscapesRootError(path)
        return p

    async def read_text_file(self, path: str) -> str:
        return self._resolve(path).read_text(encoding="utf-8")

    async def read_multiple_files(self, paths: list[str]) -> str:
        parts = []
        for path in paths:
            content = await self.read_text_file(path)
            parts.append(f"--- {path} ---\n{content}")
        return "\n".join(parts)

    async def write_file(self, path: str, content: str) -> str:
        p = self._resolve(path, write=True)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"

    async def append_file(self, path: str, content: str) -> str:
        p = self._resolve(path, write=True)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(content)
        return f"Appended {len(content)} bytes to {path}"

    async def edit_file(
        self, path: str, edits: list[FileEdit], dry_run: bool = False
    ) -> str:
        p = self._resolve(path, write=True)
        content = p.read_text(encoding="utf-8")
        for edit in edits:
            if edit.old_text not in content:
                raise ValueError(f"old_text not found: {edit.old_text!r}")
            content = content.replace(edit.old_text, edit.new_text, 1)
        if not dry_run:
            p.write_text(content, encoding="utf-8")
        return f"Edited {path}" if not dry_run else f"Dry-run edit for {path}"

    async def create_directory(self, path: str) -> str:
        p = self._resolve(path, write=True)
        p.mkdir(parents=True, exist_ok=True)
        return f"Created directory {path}"

    async def move_file(self, source: str, destination: str) -> str:
        src = self._resolve(source, write=True)
        dst = self._resolve(destination, write=True)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Moved {source} to {destination}"

    async def copy_file(self, source: str, destination: str) -> str:
        src = self._resolve(source, write=True)
        dst = self._resolve(destination, write=True)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(src), str(dst))
        return f"Copied {source} to {destination}"

    async def list_directory(self, path: str) -> list[str]:
        p = self._resolve(path)
        return sorted(entry.name for entry in p.iterdir())

    async def search_files(self, path: str, pattern: str) -> list[str]:
        p = self._resolve(path)
        matches = [m for m in p.rglob(pattern) if m.is_file()]
        return sorted(m.relative_to(self.root_dir).as_posix() for m in matches)

    async def directory_tree(self, path: str) -> str:
        p = self._resolve(path)
        entries = sorted(p.rglob("*"), key=lambda e: str(e))
        lines = []
        for entry in entries:
            rel = entry.relative_to(p)
            depth = len(rel.parts) - 1
            lines.append("  " * depth + entry.name)
        return "\n".join(lines)

    async def get_file_info(self, path: str) -> str:
        p = self._resolve(path)
        st = p.stat()
        return f"{path}: size={st.st_size} is_dir={p.is_dir()}"
