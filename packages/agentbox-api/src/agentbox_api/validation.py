from pathlib import Path
from urllib.parse import urlparse


def required_name(value: str, field: str = "name") -> str:
    text = value.strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def required_password(value: str, field: str = "password") -> str:
    if not value.strip():
        raise ValueError(f"{field} is required")
    return value


def checked_directory(value: str, field: str = "path") -> str:
    text = value.strip()
    if not text:
        raise ValueError(f"{field} is required")
    if not Path(text).expanduser().resolve().is_dir():
        raise ValueError(f"{field} must be an existing directory")
    return text


def checked_extra_roots(values: list[str]) -> list[str]:
    roots: list[str] = []
    for value in values:
        text = value.strip()
        path = Path(text).expanduser()
        if not text or not path.is_absolute() or not path.resolve().is_dir():
            raise ValueError("Each additional folder must be an absolute existing directory")
        roots.append(text)
    return roots


def optional_http_url(value: str | None, field: str) -> str | None:
    if value is None or value == "":
        return value
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"{field} must be an http/https URL")
    return value
