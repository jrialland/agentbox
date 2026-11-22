from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from loguru import logger


@dataclass(frozen=True)
class StoredFile:
    storage_path: str
    media_type: str
    size_bytes: int
    sha256: str


class MediaStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _validate_category(self, category: str) -> str:
        cleaned = category.strip("/")
        if not cleaned or ".." in Path(cleaned).parts:
            raise ValueError("invalid media category")
        return cleaned

    def _validate_suffix(self, suffix: str) -> str:
        if not suffix:
            return ""
        if (
            not suffix.startswith(".")
            or "/" in suffix
            or "\\" in suffix
            or ".." in suffix
        ):
            raise ValueError("invalid media suffix")
        return suffix

    def _safe_path(self, storage_path: str) -> Path:
        rel = Path(storage_path)
        if (
            rel.is_absolute()
            or PureWindowsPath(storage_path).is_absolute()
            or ".." in rel.parts
        ):
            raise ValueError("invalid media path")
        target = (self.root / rel).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError("invalid media path")
        return target

    def save(
        self,
        data: bytes,
        *,
        category: str,
        media_type: str,
        suffix: str = "",
    ) -> StoredFile:
        category = self._validate_category(category)
        suffix = self._validate_suffix(suffix)
        rel = f"{category}/{uuid.uuid4().hex}{suffix}"
        target = self._safe_path(rel)
        target.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, target)
        except Exception:
            Path(tmp_name).unlink(missing_ok=True)
            raise

        return StoredFile(
            storage_path=rel,
            media_type=media_type,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )

    def path(self, storage_path: str) -> Path:
        return self._safe_path(storage_path)

    def read(self, storage_path: str) -> bytes:
        return self.path(storage_path).read_bytes()

    def exists(self, storage_path: str) -> bool:
        return self.path(storage_path).is_file()

    def delete(self, storage_path: str) -> None:
        try:
            self.path(storage_path).unlink()
        except FileNotFoundError:
            logger.warning("media file missing path={}", storage_path)
