from __future__ import annotations

import ipaddress
import pathlib
import re
from typing import Any
from urllib.parse import urlparse

RESERVED_ENV = {"PLUGIN_ROOT", "PLUGIN_DATA"}
HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


def ensure_inside(root: pathlib.Path, target: pathlib.Path) -> pathlib.Path:
    resolved_root = root.resolve()
    resolved = target.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"path escapes plugin root: {target}")
    return resolved


def expand(value: str, root: pathlib.Path, data_root: pathlib.Path) -> str:
    return value.replace("${PLUGIN_ROOT}", str(root)).replace(
        "${PLUGIN_DATA}", str(data_root)
    )


def resolve_cwd(value: str, root: pathlib.Path, data_root: pathlib.Path) -> str:
    if not value:
        return str(root)
    if value == "${PLUGIN_ROOT}" or value.startswith("${PLUGIN_ROOT}/"):
        suffix = value[len("${PLUGIN_ROOT}") :].lstrip("/\\")
        return str(ensure_inside(root, root / suffix))
    if value == "${PLUGIN_DATA}" or value.startswith("${PLUGIN_DATA}/"):
        suffix = value[len("${PLUGIN_DATA}") :].lstrip("/\\")
        return str(ensure_inside(data_root, data_root / suffix))
    if value.startswith("./"):
        return str(ensure_inside(root, root / value[2:]))
    raise ValueError("cwd must start with ./, ${PLUGIN_ROOT}, or ${PLUGIN_DATA}")


def is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url must be an absolute http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("url must not contain user information")
    if parsed.fragment:
        raise ValueError("url must not contain a fragment")
    if parsed.scheme == "http" and not is_loopback(parsed.hostname):
        raise ValueError("non-loopback URLs must use https")


def validate_headers(headers: dict[str, Any]) -> dict[str, str]:
    seen: set[str] = set()
    result: dict[str, str] = {}
    for name, value in headers.items():
        if not HEADER_NAME.match(name):
            raise ValueError(f"invalid header name: {name!r}")
        lowered = name.lower()
        if lowered in seen:
            raise ValueError(f"duplicate header name: {name!r}")
        seen.add(lowered)
        result[name] = str(value)
    return result
