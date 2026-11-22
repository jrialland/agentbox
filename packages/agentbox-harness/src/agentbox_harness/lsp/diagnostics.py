import asyncio
import contextlib
import pathlib
import time
from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Protocol

from loguru import logger

from agentbox_harness.lsp.manager import LspManager, get_lsp_manager
from agentbox_harness.lsp.stacks import language_for
from agentbox_harness.session import Session


@dataclass(frozen=True)
class DiagnosticsSnapshot:
    path: str
    stack: str
    root: str
    generation: int
    state: str
    diagnostics: tuple[dict, ...] = ()
    updated_at: float = 0.0
    error: str | None = None

    @property
    def errors(self) -> list[dict]:
        return [d for d in self.diagnostics if d.get("severity", 1) == 1]

    @property
    def warnings(self) -> list[dict]:
        return [d for d in self.diagnostics if d.get("severity", 1) == 2]


@dataclass(frozen=True)
class _Job:
    session_id: str
    project_root: str
    path: str


class SessionReminder(Protocol):
    async def reminder(self, session: Session) -> str | None: ...


def _position(diagnostic: dict) -> tuple[int, int]:
    start = diagnostic.get("range", {}).get("start", {})
    return start.get("line", 0) + 1, start.get("character", 0) + 1


def _level(severity: int) -> str:
    if severity == 1:
        return "error"
    if severity == 2:
        return "warning"
    if severity == 3:
        return "info"
    return "hint"


def _source(diagnostic: dict) -> str:
    return f" ({diagnostic['source']})" if diagnostic.get("source") else ""


def _format_line(diagnostic: dict) -> str:
    line, column = _position(diagnostic)
    severity = int(diagnostic.get("severity", 1))
    message = diagnostic.get("message", "")
    return f"  {line}:{column} {_level(severity)} {message}{_source(diagnostic)}"


def _keep(diagnostic: dict, severity: str) -> bool:
    value = int(diagnostic.get("severity", 1))
    if severity == "error":
        return value == 1
    if severity == "warning":
        return value == 2
    return True


def format_snapshot(
    snapshot: DiagnosticsSnapshot, severity: str = "error", limit: int = 20
) -> str:
    limit = max(1, min(limit, 100))
    if snapshot.state == "error" and not snapshot.diagnostics:
        return f"LSP unavailable for {snapshot.path}: {snapshot.error or 'unknown error'}"
    selected = [d for d in snapshot.diagnostics if _keep(d, severity)]
    if not selected:
        return f"No LSP diagnostics for {snapshot.path}."
    errors = len(snapshot.errors)
    warnings = len(snapshot.warnings)
    header = (
        f"LSP diagnostics for {snapshot.path} "
        f"({snapshot.stack or 'unknown'}, {errors} errors, {warnings} warnings)"
    )
    lines = [header]
    lines.extend(_format_line(d) for d in selected[:limit])
    if len(selected) > limit:
        lines.append(f"  ... and {len(selected) - limit} more")
    if snapshot.state == "timeout":
        lines.append("  (analysis timed out; showing cached results)")
    return "\n".join(lines)


def format_project(
    snapshots: list[DiagnosticsSnapshot], severity: str = "error", limit: int = 20
) -> str:
    limit = max(1, min(limit, 100))
    rows: list[tuple[str, list[dict]]] = []
    total = 0
    for snapshot in snapshots:
        selected = [d for d in snapshot.diagnostics if _keep(d, severity)]
        if selected:
            rows.append((snapshot.path, selected))
            total += len(selected)
    if not rows:
        return "No LSP diagnostics for this session."
    lines = [f"LSP diagnostics ({total} findings across {len(rows)} files):"]
    shown = 0
    for path, diagnostics in rows:
        if shown >= limit:
            break
        lines.append(path)
        for diagnostic in diagnostics:
            if shown >= limit:
                break
            lines.append(_format_line(diagnostic))
            shown += 1
    if total > shown:
        lines.append(f"  ... and {total - shown} more")
    return "\n".join(lines)


class DiagnosticsService:
    def __init__(
        self,
        manager: LspManager | None = None,
        *,
        max_wait: float = 5.0,
        session_limit: int = 100,
    ):
        self.manager = manager or get_lsp_manager()
        self.max_wait = max_wait
        self.session_limit = session_limit
        self.mode = "auto"
        self.enabled = True
        self.warm_on_start = False
        self._queued: dict[pathlib.Path, _Job] = {}
        self._wake = asyncio.Event()
        self._worker: asyncio.Task | None = None
        self._snapshots: dict[pathlib.Path, DiagnosticsSnapshot] = {}
        self._inflight: dict[pathlib.Path, asyncio.Future] = {}
        self._touched: dict[str, set[pathlib.Path]] = defaultdict(set)
        self._delivered: dict[tuple[str, pathlib.Path], int] = {}
        self._analysis_count = 0

    def configure(self, settings) -> None:
        self.mode = getattr(settings, "lsp_mode", "auto")
        self.enabled = bool(
            getattr(settings, "lsp_enabled", True) and self.mode != "off"
        )
        self.max_wait = getattr(
            settings, "lsp_diagnostics_timeout", self.max_wait
        )
        self.session_limit = getattr(
            settings, "lsp_session_snapshot_limit", self.session_limit
        )
        self.warm_on_start = bool(
            getattr(settings, "lsp_warm_on_start", self.warm_on_start)
        )

    def note_write(self, session_id: str, project_root: str, path: str) -> None:
        if not self.enabled:
            return
        target = pathlib.Path(path).resolve()
        self._touched[session_id].add(target)
        if self.mode != "auto":
            return
        self._queued[target] = _Job(session_id, project_root, str(target))
        self._wake.set()
        self._ensure_worker()

    async def refresh(
        self,
        session_id: str,
        project_root: str,
        path: str,
        *,
        timeout: float | None = None,
    ) -> DiagnosticsSnapshot:
        target = pathlib.Path(path).resolve()
        self._touched[session_id].add(target)
        loop = asyncio.get_running_loop()
        future = self._inflight.get(target)
        if future is None or future.done():
            future = loop.create_future()
            self._inflight[target] = future
        self._queued[target] = _Job(session_id, project_root, str(target))
        self._wake.set()
        self._ensure_worker()
        try:
            return await asyncio.wait_for(
                future, timeout if timeout is not None else self.max_wait
            )
        except TimeoutError:
            snapshot = self._snapshots.get(target)
            if snapshot is None:
                snapshot = DiagnosticsSnapshot(
                    str(target),
                    "",
                    project_root,
                    0,
                    "timeout",
                    updated_at=time.time(),
                )
            else:
                snapshot = replace(
                    snapshot, state="timeout", updated_at=time.time()
                )
            self._snapshots[target] = snapshot
            return snapshot

    def snapshot(self, path: str) -> DiagnosticsSnapshot | None:
        return self._snapshots.get(pathlib.Path(path).resolve())

    def snapshots_for_session(self, session_id: str) -> list[DiagnosticsSnapshot]:
        paths = list(self._touched.get(session_id, ()))[: self.session_limit]
        return [
            self._snapshots[path]
            for path in paths
            if path in self._snapshots
        ]

    def project_snapshot(self, project_root: str) -> list[DiagnosticsSnapshot]:
        root = pathlib.Path(project_root).resolve()
        return [
            snapshot
            for path, snapshot in self._snapshots.items()
            if root == path or root in path.parents
        ]

    async def reminder(self, session_id: str) -> str | None:
        if not self.enabled or self.mode != "auto":
            return None
        included: list[tuple[str, list[dict]]] = []
        for path in self._touched.get(session_id, ()):
            snapshot = self._snapshots.get(path)
            if (
                snapshot is None
                or snapshot.state != "ready"
                or not snapshot.errors
            ):
                continue
            if snapshot.generation <= self._delivered.get(
                (session_id, path), -1
            ):
                continue
            included.append((snapshot.path, snapshot.errors))
            if len(included) >= 5:
                break
        if not included:
            return None
        lines = [
            "<lsp_diagnostics>",
            f"{len(included)} file(s) have errors after your edits:",
        ]
        for path, errors in included:
            for diagnostic in errors[:3]:
                line, column = _position(diagnostic)
                lines.append(
                    f"- {path}:{line}:{column} "
                    f"{diagnostic.get('message', '')}{_source(diagnostic)}"
                )
            snapshot = self._snapshots[pathlib.Path(path)]
            self._delivered[(session_id, pathlib.Path(path))] = (
                snapshot.generation
            )
        lines.append("Call lsp_diagnostics for full details.")
        lines.append("</lsp_diagnostics>")
        return "\n".join(lines)

    def _ensure_worker(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            jobs = list(self._queued.values())
            self._queued.clear()
            if jobs:
                await asyncio.gather(*(self._process(job) for job in jobs))

    def _base_snapshot(self, job: _Job, state: str, error: str | None = None):
        previous = self._snapshots.get(pathlib.Path(job.path))
        if previous is None:
            return DiagnosticsSnapshot(
                job.path,
                "",
                job.project_root,
                0,
                state,
                updated_at=time.time(),
                error=error,
            )
        return replace(
            previous, state=state, updated_at=time.time(), error=error
        )

    async def _process(self, job: _Job) -> None:
        target = pathlib.Path(job.path)
        self._analysis_count += 1
        try:
            resolved = await self.manager.server_for_path(
                job.project_root, job.path
            )
            if resolved is None:
                snapshot = self._base_snapshot(
                    job, "error", "LSP server unavailable"
                )
            else:
                stack, root, server = resolved
                language = language_for(stack, job.path)
                if language is None:
                    snapshot = self._base_snapshot(
                        job, "error", "Unsupported language"
                    )
                else:
                    generation = await server.sync_document(
                        job.path, language, save=stack.save
                    )
                    diagnostics = await server.diagnostics(job.path)
                    snapshot = DiagnosticsSnapshot(
                        job.path,
                        stack.name,
                        str(root),
                        generation,
                        "ready",
                        tuple(diagnostics),
                        time.time(),
                    )
        except TimeoutError:
            snapshot = self._base_snapshot(
                job, "timeout", "LSP analysis timed out"
            )
        except Exception as exc:
            logger.exception(
                "lsp diagnostics job failed path={}", job.path
            )
            snapshot = self._base_snapshot(job, "error", str(exc))
        self._snapshots[target] = snapshot
        future = self._inflight.pop(target, None)
        if future is not None and not future.done():
            future.set_result(snapshot)

    async def shutdown(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None
        for future in self._inflight.values():
            if not future.done():
                future.set_result(
                    DiagnosticsSnapshot(
                        "", "", "", 0, "error", error="service stopped"
                    )
                )
        self._inflight.clear()


_service = DiagnosticsService()


def get_diagnostics_service() -> DiagnosticsService:
    return _service


def configure_diagnostics(settings) -> None:
    _service.configure(settings)


class DiagnosticsReminder:
    def __init__(self, service: DiagnosticsService):
        self.service = service

    async def reminder(self, session: Session) -> str | None:
        return await self.service.reminder(session.session_id)


def make_lsp_notify_hook(service, session_id: str | None, project_root: str):
    from agentbox_harness.lsp.hooks import WRITE_TOOLS
    from agentbox_harness.tools.registry import ToolHookContext

    async def hook(ctx: ToolHookContext) -> str | None:
        if ctx.tool_name not in WRITE_TOOLS or not session_id:
            return None
        path = ctx.args.get("path")
        if not path:
            return None
        service.note_write(session_id, project_root, str(path))
        return None

    return hook


def make_lsp_diagnostics_tool(
    service: DiagnosticsService, session_id: str, project_root: str
):
    root = pathlib.Path(project_root).resolve()

    async def lsp_diagnostics(
        path: str | None = None,
        severity: str = "error",
        limit: int = 20,
    ) -> str:
        """Return LSP diagnostics for an edited file or the current session.

        Args:
            path: File path relative to the project root, or an absolute path.
                Omit to return cached results for files touched in this session.
            severity: "error" (default), "warning", or "all".
            limit: Maximum number of findings to return.
        """
        if severity not in {"error", "warning", "all"}:
            return "severity must be error, warning, or all"
        if path:
            candidate = pathlib.Path(path)
            target = (
                candidate if candidate.is_absolute() else root / candidate
            ).resolve()
            if target != root and root not in target.parents:
                return "path is outside the project"
            snapshot = await service.refresh(
                session_id, project_root, str(target)
            )
            return format_snapshot(snapshot, severity, limit)
        return format_project(
            service.snapshots_for_session(session_id), severity, limit
        )

    return lsp_diagnostics
