from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from loguru import logger
from pydantic_ai.mcp import MCPToolset

from agentbox_harness.spec import McpToolBinding
from agentbox_harness.tools.mcp import build_mcp_toolset, mcp_toolset_id
from agentbox_harness.tools.paths import resolve_project_path


@dataclass(frozen=True)
class McpWarning:
    server_id: str
    message: str


@dataclass
class SessionToolsets:
    toolsets: list[MCPToolset] = field(default_factory=list)
    warnings: list[McpWarning] = field(default_factory=list)


@dataclass
class _SessionEntry:
    bindings: list[McpToolBinding]
    toolsets: list[MCPToolset]
    warnings: list[McpWarning]
    last_used: float


class McpSessionManager:
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
        stdio = [b for b in bindings if isinstance(b, McpToolBinding) and b.command]
        entry = self._entries.get(session_id)
        if entry is not None:
            entry.last_used = self._clock()
            return SessionToolsets(list(entry.toolsets))
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
        server_id = mcp_toolset_id(binding)
        cwd = resolve_project_path(binding.cwd, project_root, extra_roots)
        try:
            toolset = build_mcp_toolset(binding, cwd=str(cwd))
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
        entry = self._entries.get(session_id)
        if entry is not None:
            entry.last_used = self._clock()

    async def close_session(self, session_id: str) -> None:
        entry = self._entries.pop(session_id, None)
        self._locks.pop(session_id, None)
        if entry is None:
            return
        for toolset in entry.toolsets:
            try:
                await toolset.__aexit__(None, None, None)
            except Exception:
                logger.warning("mcp toolset close failed session={}", session_id)

    async def close_all(self) -> None:
        for session_id in list(self._entries):
            await self.close_session(session_id)


_manager: McpSessionManager | None = None


def get_mcp_session_manager() -> McpSessionManager:
    global _manager
    if _manager is None:
        _manager = McpSessionManager()
    return _manager


def reset_mcp_session_manager() -> None:
    global _manager
    _manager = None
