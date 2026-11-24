"""Filesystem-backed media storage rooted at the configured media directory.

Files are stored under ``<root>/<category>/<uuid><suffix>`` and every returned
:class:`StoredFile` records the size and SHA-256 checksum of the written bytes.
Callers persist the storage path in the database and delete the file through
:meth:`MediaStore.delete`; cleanup is best-effort, so a missing file only logs a
warning. All paths are validated against the root so stored paths cannot escape
it.
"""

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
    """Metadata for a file written by the media store.

    ``storage_path`` is relative to the store root; ``size_bytes`` and
    ``sha256`` describe the persisted bytes for integrity checks.
    """

    storage_path: str
    media_type: str
    size_bytes: int
    sha256: str


class MediaStore:
    """Read and write media files under a single resolved root directory.

    The root is created on construction, and every path crossing the API is
    validated to stay inside it.
    """

    def __init__(self, root: str | Path):
        """Resolve and create the store root directory.

        Args:
            root: Directory media files are stored under.
        """
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
        # Reject absolute paths (POSIX or Windows) and any ``..`` segment before
        # resolving, then confirm the resolved target is the root or inside it.
        # The check compares resolved paths so symlinks cannot escape the root.
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
        """Write bytes under a category and return their stored metadata.

        The file name is a fresh UUID plus ``suffix``. Writes go to a temporary
        file in the destination directory, are flushed and fsynced, then
        atomically replaced into place; a failed write removes the temp file.

        Args:
            data: Raw bytes to persist.
            category: Subdirectory (relative to the root) to store under.
            media_type: MIME type recorded on the returned metadata.
            suffix: Optional extension beginning with ``.``.

        Returns:
            Metadata for the newly written file.

        Raises:
            ValueError: If the category or suffix is invalid.
        """
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
        """Resolve a stored path to an absolute path inside the root.

        Args:
            storage_path: Root-relative path previously returned by :meth:`save`.

        Returns:
            The resolved absolute path.

        Raises:
            ValueError: If the path escapes the store root.
        """
        return self._safe_path(storage_path)

    def read(self, storage_path: str) -> bytes:
        """Read a stored file's bytes.

        Args:
            storage_path: Root-relative path to read.

        Returns:
            The file's bytes.
        """
        return self.path(storage_path).read_bytes()

    def exists(self, storage_path: str) -> bool:
        """Return whether a stored path exists as a regular file.

        Args:
            storage_path: Root-relative path to check.

        Returns:
            ``True`` if the path resolves to an existing file.
        """
        return self.path(storage_path).is_file()

    def delete(self, storage_path: str) -> None:
        """Delete a stored file, tolerating an already-missing file.

        Args:
            storage_path: Root-relative path to delete.
        """
        try:
            self.path(storage_path).unlink()
        except FileNotFoundError:
            logger.warning("media file missing path={}", storage_path)
