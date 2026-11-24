"""Validation and path-safety helpers shared by plugin loaders.

Confines plugin-provided paths to their roots, expands ``${PLUGIN_ROOT}`` and
``${PLUGIN_DATA}`` placeholders, and validates hook/MCP URLs and headers. These
checks are the security boundary for untrusted plugin content.
"""

from __future__ import annotations

import ipaddress
import pathlib
import re
from typing import Any
from urllib.parse import urlparse

RESERVED_ENV = {"PLUGIN_ROOT", "PLUGIN_DATA"}
HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


def ensure_inside(root: pathlib.Path, target: pathlib.Path) -> pathlib.Path:
    """Resolve ``target`` and require it to stay within ``root``.

    Args:
        root: Directory considered the containment boundary.
        target: Path to resolve and check.

    Returns:
        The resolved target path.

    Raises:
        ValueError: If the resolved target escapes ``root``.
    """
    resolved_root = root.resolve()
    resolved = target.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"path escapes plugin root: {target}")
    return resolved


def expand(value: str, root: pathlib.Path, data_root: pathlib.Path) -> str:
    """Substitute plugin root and data placeholders in ``value``.

    Args:
        value: String that may contain ``${PLUGIN_ROOT}`` or ``${PLUGIN_DATA}``.
        root: Plugin root directory.
        data_root: Per-plugin writable data directory.

    Returns:
        The string with placeholders replaced.
    """
    return value.replace("${PLUGIN_ROOT}", str(root)).replace(
        "${PLUGIN_DATA}", str(data_root)
    )


def resolve_cwd(value: str, root: pathlib.Path, data_root: pathlib.Path) -> str:
    """Resolve a hook/MCP working directory against a permitted root.

    Only ``./`` paths, ``${PLUGIN_ROOT}``, and ``${PLUGIN_DATA}`` prefixes are
    accepted so working directories cannot point outside the plugin.

    Args:
        value: Working directory expression from plugin configuration.
        root: Plugin root directory.
        data_root: Per-plugin writable data directory.

    Returns:
        The resolved absolute directory path.

    Raises:
        ValueError: If ``value`` uses an unsupported prefix or escapes a root.
    """
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
    """Return whether ``host`` names the local machine.

    Args:
        host: Hostname or IP address, or ``None``.

    Returns:
        ``True`` for ``localhost`` or a loopback IP, otherwise ``False``.
    """
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_url(url: str) -> None:
    """Validate a plugin hook/MCP URL.

    Plain ``http`` is only allowed for loopback hosts; remote endpoints must use
    ``https``. Credentials and fragments are rejected to avoid leaking secrets
    and to keep requests unambiguous.

    Args:
        url: Absolute URL to validate.

    Raises:
        ValueError: If the URL is not absolute http(s), is malformed, contains
            user information or a fragment, or uses non-loopback plain http.
    """
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
    """Validate HTTP header names and stringify their values.

    Args:
        headers: Header mapping from plugin configuration.

    Returns:
        A copy of the headers with values coerced to strings.

    Raises:
        ValueError: If a header name is invalid or duplicated case-insensitively.
    """
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
