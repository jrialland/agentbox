"""Manage language-server processes by project root and stack.

The manager detects stacks per project, starts one :class:`LspServer` per
``(root, stack)`` pair on demand, tracks active servers per session, and applies
exponential failure backoff so a broken server is not retried on every write.
"""

import asyncio
import json
import pathlib
import time

from loguru import logger

from agentbox_harness.lsp.client import LspServer
from agentbox_harness.lsp.detect import detect_stacks, nearest_root
from agentbox_harness.lsp.stacks import (
    DEFAULT_LSP_SERVERS,
    LspStack,
    stack_for_path,
)


class LspManager:
    """Registry of live language servers plus detection and failure state.

    Servers are keyed by resolved project root and stack name. Starting a server
    is async and may spawn a subprocess; detection walks the project once and is
    cached per root until :meth:`reset` clears it.
    """

    def __init__(self):
        self.enabled = True
        self.initialize_timeout = 10.0
        self.diagnostics_timeout = 5.0
        self.failure_backoff = 60.0
        self.first_change_timeout = 1.0
        self.settle_window = 0.3
        self.max_open_documents = 50
        self.stacks = None
        self._servers = {}
        self._detected = {}
        self._active = {}
        self._failure_attempts = {}
        self._failed_at = {}

    def configure(self, settings):
        """Apply LSP settings, including optional custom stack definitions.

        Args:
            settings: Settings object exposing the ``lsp_*`` attributes. Custom
                stacks are parsed from ``lsp_servers_json`` when present.
        """
        self.enabled = settings.lsp_enabled
        self.initialize_timeout = settings.lsp_initialize_timeout
        self.diagnostics_timeout = settings.lsp_diagnostics_timeout
        self.failure_backoff = settings.lsp_failure_backoff_seconds
        self.first_change_timeout = getattr(
            settings, "lsp_first_change_timeout", self.first_change_timeout
        )
        self.settle_window = getattr(
            settings, "lsp_settle_window", self.settle_window
        )
        self.max_open_documents = getattr(
            settings, "lsp_max_open_documents", self.max_open_documents
        )
        if settings.lsp_servers_json:
            self.stacks = [
                LspStack(**entry)
                for entry in json.loads(settings.lsp_servers_json)
            ]

    def _all_stacks(self):
        return DEFAULT_LSP_SERVERS if self.stacks is None else self.stacks

    def detected(self, project_root):
        """Return cached stacks detected for a project root.

        Args:
            project_root: Project root whose stack list is wanted.

        Returns:
            Detected stacks, computed on first use and cached thereafter.
        """
        key = str(pathlib.Path(project_root).resolve())
        if key not in self._detected:
            self._detected[key] = detect_stacks(key, self.stacks)
        return self._detected[key]

    def resolve_root(self, stack, path, project_root):
        """Return the nearest workspace root for a stack and file path.

        Args:
            stack: Stack whose root markers guide the search.
            path: File path being analyzed.
            project_root: Fallback root when no marker matches.

        Returns:
            The resolved workspace root.
        """
        return nearest_root(stack, path, project_root)

    async def server_for_path(self, project_root, path):
        """Resolve a path to its stack, root, and running server.

        Args:
            project_root: Project root used as detection and root fallback.
            path: File path to analyze.

        Returns:
            A ``(stack, root, server)`` tuple, or ``None`` when no stack matches
            the path or the server cannot start.
        """
        stack = stack_for_path(self._all_stacks(), path)
        if stack is None:
            return None
        root = self.resolve_root(stack, path, project_root)
        server = await self.get_or_start(str(root), stack)
        if server is None:
            return None
        return stack, root, server

    def _retry_delay(self, key) -> float:
        # Exponential backoff capped by failure_backoff: 1s, 2s, 4s, ...
        attempts = self._failure_attempts.get(key, 0)
        return min(self.failure_backoff, float(2 ** max(0, attempts - 1)))

    async def get_or_start(self, project_root, stack):
        """Return a live server for a root and stack, starting one if needed.

        This async method may spawn a subprocess. Failures are rate-limited by
        backoff so repeated writes do not repeatedly pay the startup timeout.

        Args:
            project_root: Workspace root for the server.
            stack: Stack describing the server command and behavior.

        Returns:
            A ready :class:`LspServer`, or ``None`` when disabled, backing off,
            or the startup attempt failed.
        """
        if not self.enabled:
            return None
        key = (str(pathlib.Path(project_root).resolve()), stack.name)
        failed_at = self._failed_at.get(key)
        if failed_at is not None and time.monotonic() - failed_at < self._retry_delay(key):
            # Still inside the backoff window after a failed start.
            return None
        server = self._servers.get(key)
        if server and not server.dead:
            return server
        if server and server.dead:
            # Reap the dead process before replacing its registry entry.
            await server.stop()
            self._servers.pop(key, None)
        try:
            server = LspServer(
                stack.command,
                project_root,
                pull=stack.pull,
                settle=stack.settle,
                quiescence=stack.quiescence,
                initialize_timeout=self.initialize_timeout,
                diagnostics_timeout=self.diagnostics_timeout,
                first_change_timeout=(
                    stack.first_change_timeout
                    if stack.first_change_timeout != 1.0
                    else self.first_change_timeout
                ),
                settle_window=(
                    stack.settle_window
                    if stack.settle_window != 0.3
                    else self.settle_window
                ),
                post_quiescence_grace=stack.post_quiescence_grace,
                max_wait=self.diagnostics_timeout,
                stderr_lines=200,
                doc_limit=self.max_open_documents,
                stack_name=stack.name,
            )
            await server.start()
            self._servers[key] = server
            self._failed_at.pop(key, None)
            self._failure_attempts.pop(key, None)
            logger.debug(
                "lsp server ready stack={} root={}", stack.name, project_root
            )
            return server
        except Exception as exc:
            self._failure_attempts[key] = (
                self._failure_attempts.get(key, 0) + 1
            )
            self._failed_at[key] = time.monotonic()
            logger.warning(
                "lsp unavailable project={} stack={} error={}",
                project_root,
                stack.name,
                exc,
            )
            return None

    async def warm(self, project_root):
        """Start every detected stack for a project concurrently.

        Startup failures are swallowed so one unavailable server does not block
        the others; a failed start is still recorded for backoff.

        Args:
            project_root: Project root whose detected stacks are warmed.
        """
        if not self.enabled:
            return
        stacks = self.detected(project_root)
        if not stacks:
            return
        await asyncio.gather(
            *(
                self.get_or_start(project_root, stack)
                for stack in stacks
            ),
            return_exceptions=True,
        )

    def record_active(self, session_id, project_root, stack, server):
        """Record that a session is using a server for a stack.

        Args:
            session_id: Session that performed the write.
            project_root: Workspace root of the server.
            stack: Stack served by ``server``.
            server: Live server instance.
        """
        self._active.setdefault(session_id, {})[stack.name] = (
            str(project_root),
            stack,
            server,
        )

    def active_for_session(self, session_id):
        """Return health summaries for the servers a session has used.

        Args:
            session_id: Session whose active servers are listed.

        Returns:
            One dictionary per stack with command, root, status, state,
            document count, and last error.
        """
        entries = []
        for project_root, stack, server in self._active.get(
            session_id, {}
        ).values():
            health_fn = getattr(server, "health", None)
            if callable(health_fn):
                health = health_fn()
            else:
                health = {
                    "state": "ready",
                    "documents": getattr(server, "documents", 0),
                    "last_error": None,
                }
            entries.append(
                {
                    "stack": stack.name,
                    "command": " ".join(stack.command),
                    "root": project_root,
                    "status": "failed" if server.dead else "running",
                    "state": health["state"],
                    "documents": health["documents"],
                    "last_error": health["last_error"],
                }
            )
        return entries

    def detected_for_project(self, project_root):
        """Return detected stack names for a project root.

        Args:
            project_root: Project root to report on.

        Returns:
            Stack names in detection order.
        """
        return [stack.name for stack in self.detected(project_root)]

    def health(self):
        """Return per-server health dictionaries for every live server."""
        entries = []
        for (root, name), server in self._servers.items():
            entry = server.health()
            entry["root"] = root
            entry["name"] = name
            entries.append(entry)
        return entries

    async def shutdown(self):
        """Stop every managed server and clear session, failure, and backoff state."""
        for server in list(self._servers.values()):
            await server.stop()
        self._servers.clear()
        self._active.clear()
        self._failed_at.clear()
        self._failure_attempts.clear()

    async def reset(self):
        """Shut down all servers and forget cached stack detection."""
        await self.shutdown()
        self._detected.clear()


_manager = LspManager()


def get_lsp_manager() -> LspManager:
    """Return the process-wide LSP manager singleton."""
    return _manager


def configure_lsp(settings):
    """Configure the process-wide LSP manager from settings.

    Args:
        settings: Settings object passed through to :meth:`LspManager.configure`.
    """
    _manager.configure(settings)
