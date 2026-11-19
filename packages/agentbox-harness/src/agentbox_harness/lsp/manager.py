import json
import time

from loguru import logger

from agentbox_harness.lsp.client import LspServer
from agentbox_harness.lsp.detect import detect_stacks
from agentbox_harness.lsp.stacks import LspStack


class LspManager:
    def __init__(self):
        self.enabled = True
        self.initialize_timeout = 10.0
        self.diagnostics_timeout = 5.0
        self.failure_backoff = 60.0
        self.stacks = None
        self._servers = {}
        self._detected = {}
        self._active = {}
        self._failed = {}

    def configure(self, settings):
        self.enabled = settings.lsp_enabled
        self.initialize_timeout = settings.lsp_initialize_timeout
        self.diagnostics_timeout = settings.lsp_diagnostics_timeout
        self.failure_backoff = settings.lsp_failure_backoff_seconds
        if settings.lsp_servers_json:
            self.stacks = [
                LspStack(**entry)
                for entry in json.loads(settings.lsp_servers_json)
            ]

    def detected(self, project_root):
        if project_root not in self._detected:
            self._detected[project_root] = detect_stacks(project_root, self.stacks)
        return self._detected[project_root]

    async def get_or_start(self, project_root, stack):
        if not self.enabled:
            return None
        key = (project_root, stack.name)
        if (
            key in self._failed
            and time.monotonic() - self._failed[key] < self.failure_backoff
        ):
            return None
        server = self._servers.get(key)
        if server and not server.dead:
            return server
        try:
            server = LspServer(
                stack.command,
                project_root,
                initialize_timeout=self.initialize_timeout,
                diagnostics_timeout=self.diagnostics_timeout,
            )
            await server.start()
            self._servers[key] = server
            self._failed.pop(key, None)
            return server
        except Exception as exc:
            logger.warning(
                "lsp unavailable project={} stack={} error={}",
                project_root,
                stack.name,
                exc,
            )
            self._failed[key] = time.monotonic()
            return None

    def record_active(self, session_id, project_root, stack, server):
        self._active.setdefault(session_id, {})[stack.name] = (
            project_root,
            stack,
            server,
        )

    def active_for_session(self, session_id):
        entries = []
        for project_root, stack, server in self._active.get(session_id, {}).values():
            entries.append(
                {
                    "stack": stack.name,
                    "command": " ".join(stack.command),
                    "root": project_root,
                    "status": "failed" if server.dead else "running",
                    "documents": server.documents,
                }
            )
        return entries

    def detected_for_project(self, project_root):
        return [stack.name for stack in self.detected(project_root)]

    async def shutdown(self):
        for server in list(self._servers.values()):
            await server.stop()
        self._servers.clear()
        self._active.clear()

    def reset(self):
        self._servers.clear()
        self._detected.clear()
        self._active.clear()
        self._failed.clear()


_manager = LspManager()


def get_lsp_manager() -> LspManager:
    return _manager


def configure_lsp(settings):
    _manager.configure(settings)
