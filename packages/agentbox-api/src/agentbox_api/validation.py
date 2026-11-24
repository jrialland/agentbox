"""Input validators shared by API routers and schemas.

These helpers raise ``ValueError`` (which FastAPI surfaces as a validation
error) on invalid input. Directory checks touch the filesystem via
``Path.resolve``/``is_dir`` and therefore reflect the server's filesystem, not
the client's.
"""

from pathlib import Path
from urllib.parse import urlparse


def required_name(value: str, field: str = "name") -> str:
    """Require a non-blank name and return it stripped.

    Args:
        value: Candidate name.
        field: Field label used in the error message.

    Returns:
        The trimmed name.

    Raises:
        ValueError: If the name is empty or whitespace only.
    """
    text = value.strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def required_password(value: str, field: str = "password") -> str:
    """Require a non-blank password, preserving surrounding characters.

    Args:
        value: Candidate password.
        field: Field label used in the error message.

    Returns:
        The password unchanged; whitespace is significant in passwords.

    Raises:
        ValueError: If the password is empty or whitespace only.
    """
    if not value.strip():
        raise ValueError(f"{field} is required")
    return value


def checked_directory(value: str, field: str = "path") -> str:
    """Require an existing directory, expanding ``~`` for the check.

    The returned value is the original text, not the resolved path, so callers
    keep the user's spelling.

    Args:
        value: Candidate directory path.
        field: Field label used in error messages.

    Returns:
        The original path text when it resolves to an existing directory.

    Raises:
        ValueError: If the path is blank, or does not resolve to an existing
            directory on the server.
    """
    text = value.strip()
    if not text:
        raise ValueError(f"{field} is required")
    if not Path(text).expanduser().resolve().is_dir():
        raise ValueError(f"{field} must be an existing directory")
    return text


def checked_extra_roots(values: list[str]) -> list[str]:
    """Validate that each extra root is an absolute, existing directory.

    Args:
        values: Directory paths to validate.

    Returns:
        The original, stripped paths in input order.

    Raises:
        ValueError: If any entry is blank, relative, or not an existing
            directory. All entries must pass; partial results are not returned.
    """
    roots: list[str] = []
    for value in values:
        text = value.strip()
        path = Path(text).expanduser()
        # Absolute paths avoid resolving against the server's working
        # directory, which would make access depend on process CWD.
        if not text or not path.is_absolute() or not path.resolve().is_dir():
            raise ValueError("Each additional folder must be an absolute existing directory")
        roots.append(text)
    return roots


def optional_http_url(value: str | None, field: str) -> str | None:
    """Require that an optional value is an ``http``/``https`` URL.

    Args:
        value: Candidate URL. ``None`` and the empty string are allowed and
            returned unchanged.
        field: Field label used in the error message.

    Returns:
        The original value when it is empty or a valid HTTP(S) URL with a
        host.

    Raises:
        ValueError: If the value has a non-HTTP(S) scheme or no host.
    """
    if value is None or value == "":
        return value
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"{field} must be an http/https URL")
    return value
