"""Proxy Agentbox filesystem and terminal tools through an ACP client.

When an ACP client advertises filesystem or terminal capabilities, the native
tools are overridden so reads, writes, and commands execute on the client side
through the ACP connection instead of the server's local filesystem.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable
from dataclasses import dataclass
from difflib import unified_diff
from typing import Any

import acp

from agentbox_api.acp_terminals import AcpTerminalTracker
from agentbox_harness.spec import AgentSpec, NativeToolBinding
from agentbox_harness.tools.filesystem import FileEdit, apply_file_edit
from agentbox_harness.tools.paths import resolve_project_path
from agentbox_harness.tools.registry import ToolRegistry
from agentbox_harness.tools.terminal import TERMINAL_TOOL_NAMES


@dataclass(frozen=True)
class AcpClientCapabilities:
    """Filesystem and terminal capabilities advertised by an ACP client."""

    read_text_file: bool = False
    write_text_file: bool = False
    terminal: bool = False

    @classmethod
    def from_sdk(cls, caps: Any) -> AcpClientCapabilities:
        """Normalize the SDK capability object into this dataclass.

        Args:
            caps: Client capability object from the ACP ``initialize`` request,
                or ``None`` when the client sent none.

        Returns:
            Capabilities with missing or unset fields treated as unsupported.
        """
        if caps is None:
            return cls()
        fs = getattr(caps, "fs", None)
        return cls(
            read_text_file=bool(getattr(fs, "read_text_file", False)),
            write_text_file=bool(getattr(fs, "write_text_file", False)),
            terminal=bool(getattr(caps, "terminal", False)),
        )


@dataclass
class AcpClientTools:
    """Client-bound state used by the proxied filesystem and terminal tools."""

    client: acp.Client
    session_id: str
    project_root: str
    extra_roots: list[str]
    capabilities: AcpClientCapabilities
    terminals: AcpTerminalTracker | None = None

    async def close(self) -> None:
        """Release any terminal resources held for this ACP session."""
        if self.terminals is not None:
            await self.terminals.close()


def _resolve(path: str, tools: AcpClientTools) -> pathlib.Path | None:
    # Only paths inside the project or an approved extra root are proxied to the
    # client; callers fall back to the native tool for anything outside.
    try:
        return resolve_project_path(path, tools.project_root, tools.extra_roots)
    except ValueError:
        return None


async def _read_text(tools: AcpClientTools, path: pathlib.Path) -> str:
    response = await tools.client.read_text_file(
        tools.session_id, str(path), line=None, limit=None
    )
    return response.content


def _make_read_text_file(tools: AcpClientTools, original: Callable) -> Callable:
    async def read_text_file(
        path: str, head: int | None = None, tail: int | None = None
    ) -> str:
        # Reject conflicting windowing arguments before touching the client.
        if head is not None and tail is not None:
            raise ValueError("head and tail are mutually exclusive")
        resolved = _resolve(path, tools)
        if resolved is None:
            return await original(path, head=head, tail=tail)
        text = await _read_text(tools, resolved)
        if head is not None:
            return "\n".join(text.splitlines()[:head])
        if tail is not None:
            return "\n".join(text.splitlines()[-tail:]) if tail else ""
        return text

    return read_text_file


def _make_read_file(tools: AcpClientTools, original: Callable) -> Callable:
    async def read_file(path: str) -> str:
        resolved = _resolve(path, tools)
        if resolved is None:
            return await original(path)
        return await _read_text(tools, resolved)

    return read_file


def _make_read_multiple_files(tools: AcpClientTools, original: Callable) -> Callable:
    async def read_multiple_files(paths: list[str]) -> str:
        targets = []
        for path in paths:
            target = _resolve(path, tools)
            if target is None:
                return await original(paths)
            targets.append(target)
        parts = []
        for path, target in zip(paths, targets, strict=True):
            try:
                parts.append(f"--- {path} ---\n{await _read_text(tools, target)}")
            except Exception as exc:
                parts.append(f"--- {path} ---\nError: {exc}")
        return "\n".join(parts)

    return read_multiple_files


def _make_write_file(tools: AcpClientTools, original: Callable) -> Callable:
    async def write_file(path: str, content: str) -> str:
        resolved = _resolve(path, tools)
        if resolved is None:
            return await original(path, content)
        if not resolved.parent.exists():
            raise ValueError(f"Parent directory does not exist: {resolved.parent}")
        await tools.client.write_text_file(tools.session_id, str(resolved), content)
        return f"Wrote {len(content)} bytes to {path}"

    return write_file


def _make_append_file(tools: AcpClientTools, original: Callable) -> Callable:
    async def append_file(path: str, content: str) -> str:
        resolved = _resolve(path, tools)
        if resolved is None:
            return await original(path, content)
        if not resolved.parent.exists():
            raise ValueError(f"Parent directory does not exist: {resolved.parent}")
        existing = await _read_text(tools, resolved) if resolved.exists() else ""
        await tools.client.write_text_file(
            tools.session_id, str(resolved), existing + content
        )
        return f"Appended {len(content)} bytes to {path}"

    return append_file


def _make_edit_file(tools: AcpClientTools, original: Callable) -> Callable:
    async def edit_file(
        path: str, edits: list[FileEdit], dry_run: bool = False
    ) -> str:
        resolved = _resolve(path, tools)
        if resolved is None:
            return await original(path, edits, dry_run=dry_run)
        raw = await _read_text(tools, resolved)
        newline = "\r\n" if "\r\n" in raw else ("\r" if "\r" in raw else "\n")
        updated = raw
        for edit in edits:
            updated = apply_file_edit(updated, edit, newline)
        if dry_run:
            diff = "".join(
                unified_diff(
                    raw.splitlines(True),
                    updated.splitlines(True),
                    fromfile=path,
                    tofile=path,
                )
            )
            return diff or "No changes"
        await tools.client.write_text_file(tools.session_id, str(resolved), updated)
        return f"Edited {path}"

    return edit_file


def _make_copy_file(tools: AcpClientTools, original: Callable) -> Callable:
    async def copy_file(source: str, destination: str) -> str:
        src = _resolve(source, tools)
        dst = _resolve(destination, tools)
        if src is None or dst is None:
            return await original(source, destination)
        if not src.is_file():
            raise ValueError("Source is not a regular file")
        if dst.exists():
            raise ValueError(f"Destination exists: {destination}")
        if not dst.parent.exists():
            raise ValueError(f"Parent directory does not exist: {dst.parent}")
        content = await _read_text(tools, src)
        await tools.client.write_text_file(tools.session_id, str(dst), content)
        return f"Copied {source} to {destination}"

    return copy_file


def install_acp_client_tools(
    registry: ToolRegistry,
    spec: AgentSpec,
    tools: AcpClientTools,
) -> None:
    """Override native tools with ACP-client-backed implementations.

    Only tools present in the agent spec and supported by the client's
    advertised capabilities are overridden; everything else keeps its native
    behavior. Read-only tools require the read capability, ``write_file``
    requires write, append/edit/copy require read and write, and terminal tools
    require the terminal capability.

    Args:
        registry: Registry whose native tools may be overridden in place.
        spec: Parsed agent spec deciding which native tools are active.
        tools: Client connection and sandbox roots used by the wrappers.
    """
    names = {
        binding.name
        for binding in spec.tool_bindings
        if isinstance(binding, NativeToolBinding)
    }

    def install(name: str, wrapper: Callable) -> None:
        if name in names and registry.get_native_raw(name) is not None:
            registry.override_native(name, wrapper)

    if tools.capabilities.read_text_file:
        for name, maker in (
            ("read_text_file", _make_read_text_file),
            ("read_file", _make_read_file),
            ("read_multiple_files", _make_read_multiple_files),
        ):
            original = registry.get_native_raw(name)
            if original is not None:
                install(name, maker(tools, original))

    if tools.capabilities.write_text_file:
        original = registry.get_native_raw("write_file")
        if original is not None:
            install("write_file", _make_write_file(tools, original))

    if tools.capabilities.read_text_file and tools.capabilities.write_text_file:
        for name, maker in (
            ("append_file", _make_append_file),
            ("edit_file", _make_edit_file),
            ("copy_file", _make_copy_file),
        ):
            original = registry.get_native_raw(name)
            if original is not None:
                install(name, maker(tools, original))

    if tools.capabilities.terminal and any(
        name in names for name in TERMINAL_TOOL_NAMES
    ):
        tracker = AcpTerminalTracker(
            tools.client,
            tools.session_id,
            tools.project_root,
            tools.extra_roots,
        )
        tools.terminals = tracker
        for name in TERMINAL_TOOL_NAMES:
            if name in names:
                registry.override_native(name, getattr(tracker, name))
