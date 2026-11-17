import pathlib


class PathEscapesRootError(Exception):
    pass


class FilesystemToolbox:
    def __init__(self, root_dir: pathlib.Path):
        self.root_dir = pathlib.Path(root_dir).resolve()

    def _resolve(self, path: str) -> pathlib.Path:
        p = (self.root_dir / path).resolve()
        if not (p == self.root_dir or self.root_dir in p.parents):
            raise PathEscapesRootError(path)
        return p

    async def read_text_file(self, path: str) -> str:
        return self._resolve(path).read_text(encoding="utf-8")

    async def write_file(self, path: str, content: str) -> str:
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"

    async def list_directory(self, path: str) -> list[str]:
        p = self._resolve(path)
        return sorted(entry.name for entry in p.iterdir())

    async def get_file_info(self, path: str) -> str:
        p = self._resolve(path)
        st = p.stat()
        return f"{path}: size={st.st_size} is_dir={p.is_dir()}"
