"""Manage long-lived MCP toolsets per agent session.

Stdio MCP servers are started lazily per session, reused across runs, closed
when the session ends, and swept when idle. Server startup failures become
warnings instead of failing the session.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from loguru import logger
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import CustomEvent

from agentbox_harness.spec import McpToolBinding
from agentbox_harness.tools.mcp import build_mcp_toolset, mcp_toolset_id
from agentbox_harness.tools.paths import resolve_project_path


@dataclass(frozen=True)
class McpWarning:
    """A non-fatal MCP startup problem for one server."""

    server_id: str
    message: str


@dataclass
class SessionToolsets:
    """Toolsets started for a session and warnings from failed servers."""

    toolsets: list[MCPToolset] = field(default_factory=list)
    warnings: list[McpWarning] = field(default_factory=list)


@dataclass(kw_only=True)
class McpWarningEvent(CustomEvent, name="mcp.warning"):
    """Custom event emitted when an MCP server fails to start."""

    server: str
    message: str


@dataclass
class _SessionEntry:
    """Cached toolsets and warnings for one session."""

    bindings: list[McpToolBinding]
    toolsets: list[MCPToolset]
    warnings: list[McpWarning]
    last_used: float


class McpSessionManager:
    """Start, reuse, and close MCP toolsets for agent sessions.

    Only stdio servers are started here; HTTP servers are managed by
    pydantic-ai. Entries are keyed by session id and guarded by a per-session
    lock so concurrent runs share one set of toolsets.
    """

    def __init__(self, start_timeout: float = 30.0) -> None:
        self.start_timeout = start_timeout
        self._entries: dict[str, _SessionEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._clock = time.monotonic

    async def toolsets_for(
        self,
        session_id: str,
        bindings: list[McpToolBinding],
        project_root: str,
        extra_roots: list[str] | None = None,
    ) -> SessionToolsets:
        """Return the toolsets for a session, starting stdio servers on use.

        Args:
            session_id: Session requesting tools.
            bindings: MCP server bindings from the Agent configuration.
            project_root: Root used to resolve server working directories.
            extra_roots: Additional allowed working directories.

        Returns:
            Cached toolsets plus warnings for servers that failed to start.
        """
        stdio = [b for b in bindings if isinstance(b, McpToolBinding) and b.command]
        entry = self._entries.get(session_id)
        if entry is not None:
            entry.last_used = self._clock()
            return SessionToolsets(list(entry.toolsets))
        # Double-check under the per-session lock so two concurrent runs do not
        # start duplicate servers for the same session.
        lock = self._locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            entry = self._entries.get(session_id)
            if entry is None:
                entry = await self._create_entry(
                    session_id, stdio, project_root, extra_roots
                )
                self._entries[session_id] = entry
            entry.last_used = self._clock()
            return SessionToolsets(list(entry.toolsets), list(entry.warnings))

    async def _create_entry(
        self,
        session_id: str,
        stdio: list[McpToolBinding],
        project_root: str,
        extra_roots: list[str] | None,
    ) -> _SessionEntry:
        """Create a session entry and start all stdio servers concurrently."""
        entry = _SessionEntry(
            bindings=stdio,
            toolsets=[],
            warnings=[],
            last_used=self._clock(),
        )
        results = await asyncio.gather(
            *(
                self._start(session_id, binding, project_root, extra_roots)
                for binding in stdio
            )
        )
        for toolset, warning in results:
            if toolset is not None:
                entry.toolsets.append(toolset)
            if warning is not None:
                entry.warnings.append(warning)
        return entry

    async def _start(
        self,
        session_id: str,
        binding: McpToolBinding,
        project_root: str,
        extra_roots: list[str] | None,
    ) -> tuple[MCPToolset | None, McpWarning | None]:
        """Start one stdio server, converting failures into warnings.

        Args:
            session_id: Session that owns the server.
            binding: MCP binding to start.
            project_root: Root used to resolve the working directory.
            extra_roots: Additional allowed working directories.

        Returns:
            The started toolset, or ``None`` with a warning when startup fails.
        """
        server_id = mcp_toolset_id(binding)
        try:
            cwd = resolve_project_path(binding.cwd, project_root, extra_roots)
        except ValueError as exc:
            logger.warning("mcp cwd rejected session={} server={}", session_id, server_id)
            return None, McpWarning(server_id, str(exc))
        try:
            toolset = build_mcp_toolset(binding, cwd=str(cwd))
            # Bound startup so one hung server cannot stall the session.
            await asyncio.wait_for(toolset.__aenter__(), timeout=self.start_timeout)
            return toolset, None
        except Exception as exc:
            logger.warning(
                "mcp server failed to start server={} error={}",
                server_id,
                type(exc).__name__,
            )
            return None, McpWarning(server_id, f"{type(exc).__name__}: {exc}")

    def touch(self, session_id: str) -> None:
        """Mark a session as recently used so idle sweeps keep its toolsets."""
        entry = self._entries.get(session_id)
        if entry is not None:
            entry.last_used = self._clock()

    async def close_session(self, session_id: str) -> None:
        """Close and forget a session's toolsets.

        Closing errors are logged and otherwise ignored so one bad server
        cannot block cleanup.
        """
        entry = self._entries.pop(session_id, None)
        self._locks.pop(session_id, None)
        if entry is None:
            return
        for toolset in entry.toolsets:
            try:
                await toolset.__aexit__(None, None, None)
            except Exception:
                logger.warning("mcp toolset close failed session={}", session_id)

    async def sweep_idle(self, ttl_seconds: float) -> None:
        """Close sessions unused for at least ``ttl_seconds``.

        Args:
            ttl_seconds: Idle timeout before a session's toolsets are closed.
        """
        now = self._clock()
        stale = [
            session_id
            for session_id, entry in list(self._entries.items())
            if now - entry.last_used >= ttl_seconds
        ]
        for session_id in stale:
            await self.close_session(session_id)
        if stale:
            logger.debug("mcp idle sweep closed count={}", len(stale))

    async def close_all(self) -> None:
        """Close toolsets for every tracked session."""
        for session_id in list(self._entries):
            await self.close_session(session_id)


_manager: McpSessionManager | None = None


def get_mcp_session_manager() -> McpSessionManager:
    """Return the process-wide MCP session manager, creating it on first use."""
    global _manager
    if _manager is None:
        _manager = McpSessionManager()
    return _manager


def reset_mcp_session_manager() -> None:
    """Discard the process-wide manager so the next call rebuilds it."""
    global _manager
    _manager = None
