"""Shell execution tools with foreground and background job support.

Commands run through the platform shell (PowerShell on Windows, ``bash``
elsewhere). Background jobs are tracked per session, their combined output is
drained asynchronously and capped in memory, and they are killed as process
trees.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import os
import pathlib
import shutil
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass, field

DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 300
MAX_OUTPUT_CHARS = 20_000
DEFAULT_TAIL_CHARS = 10_000
MAX_TAIL_CHARS = 100_000
JOB_OUTPUT_LIMIT = 200_000
MAX_JOBS_PER_SESSION = 20

TERMINAL_TOOL_NAMES = (
    "run_command",
    "list_jobs",
    "get_job_output",
    "kill_job",
)


def shell_command(command: str) -> list[str]:
    """Build the argv used to run a command through the platform shell.

    On Windows the command is wrapped in a PowerShell script that propagates
    the native exit code, then passed with ``-EncodedCommand`` to avoid quoting
    issues. Elsewhere it runs through ``bash -c``.

    Args:
        command: Shell command to execute.

    Returns:
        Arguments for ``asyncio.create_subprocess_exec``.
    """
    if os.name == "nt":
        shell = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
        # PowerShell only sets $LASTEXITCODE for native commands, so fall back
        # to $? when the command was a PowerShell cmdlet.
        wrapped = (
            f"{command}\n"
            "$agentbox_ok = $?\n"
            "if ($null -ne $LASTEXITCODE) { exit $LASTEXITCODE }\n"
            "if (-not $agentbox_ok) { exit 1 }\n"
        )
        encoded = base64.b64encode(wrapped.encode("utf-16-le")).decode("ascii")
        return [shell, "-NoProfile", "-EncodedCommand", encoded]
    shell = shutil.which("bash") or "/bin/sh"
    return [shell, "-c", command]


@dataclass
class Job:
    """A running or finished shell job and its buffered output.

    Attributes:
        output: Buffer capped at the manager limit; the oldest bytes are
            dropped and ``truncated`` is set when it overflows.
        drain_task: Task that reads process output until the process exits.
    """

    id: str
    session_id: str
    command: str
    cwd: pathlib.Path
    process: asyncio.subprocess.Process
    output: bytearray = field(default_factory=bytearray)
    truncated: bool = False
    status: str = "running"
    exit_code: int | None = None
    timed_out: bool = False
    started_at: float = field(default_factory=time.monotonic)
    ended_at: float | None = None
    drain_task: asyncio.Task | None = None


class JobManager:
    """Start, track, and terminate shell jobs per session.

    Each session has its own job table limited to ``max_jobs``. Combined
    stdout/stderr is drained asynchronously and capped in memory, and starts
    within a session are serialized by a lock.
    """

    def __init__(
        self,
        *,
        output_limit: int = JOB_OUTPUT_LIMIT,
        max_jobs: int = MAX_JOBS_PER_SESSION,
    ):
        self._output_limit = output_limit
        self._max_jobs = max_jobs
        self._sessions: dict[str, dict[str, Job]] = {}
        self._lock = asyncio.Lock()

    async def start(self, session_id: str, command: str, cwd: pathlib.Path) -> Job:
        """Start a background job for a session.

        Args:
            session_id: Session that owns the job.
            command: Shell command to run.
            cwd: Working directory for the process.

        Returns:
            The started job; its output is drained by a background task.

        Raises:
            RuntimeError: If the session already has the maximum number of
                jobs.
        """
        async with self._lock:
            jobs = self._sessions.setdefault(session_id, {})
            if len(jobs) >= self._max_jobs:
                raise RuntimeError(
                    f"Job limit reached ({self._max_jobs}); kill a job first."
                )
            job_id = uuid.uuid4().hex[:8]
            while job_id in jobs:
                job_id = uuid.uuid4().hex[:8]
            process = await self._spawn(command, cwd)
            job = Job(
                id=job_id,
                session_id=session_id,
                command=command,
                cwd=cwd,
                process=process,
            )
            jobs[job.id] = job
        job.drain_task = asyncio.create_task(self._drain(job))
        return job

    async def _spawn(
        self, command: str, cwd: pathlib.Path
    ) -> asyncio.subprocess.Process:
        """Spawn the process in its own group so kills reach child processes."""
        kwargs: dict = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        return await asyncio.create_subprocess_exec(
            *shell_command(command),
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            **kwargs,
        )

    async def _drain(self, job: Job) -> None:
        """Read combined output into the job buffer until the process exits.

        Output is capped at ``output_limit`` bytes; on overflow the oldest bytes
        are dropped and ``truncated`` is set. The exit status is finalized here.
        """
        assert job.process.stdout is not None
        try:
            while True:
                chunk = await job.process.stdout.read(65536)
                if not chunk:
                    break
                job.output.extend(chunk)
                if len(job.output) > self._output_limit:
                    # Keep the tail of the output, which is usually the most
                    # useful part, and remember that earlier bytes were lost.
                    overflow = len(job.output) - self._output_limit
                    del job.output[:overflow]
                    job.truncated = True
        finally:
            code = await job.process.wait()
            job.exit_code = code
            if job.status == "running":
                job.status = "completed" if code == 0 else "failed"
            job.ended_at = time.monotonic()

    async def _terminate(self, job: Job) -> None:
        """Kill a running job and wait briefly for it to exit.

        Windows uses ``taskkill /T`` to reach the process tree; other platforms
        signal the process group.
        """
        if job.status != "running":
            return
        job.status = "killed"
        job.ended_at = time.monotonic()
        if os.name == "nt":
            try:
                killer = await asyncio.create_subprocess_exec(
                    "taskkill",
                    "/F",
                    "/T",
                    "/PID",
                    str(job.process.pid),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await killer.wait()
            except OSError:
                pass
        else:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(job.process.pid), signal.SIGKILL)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(job.process.wait(), timeout=5)

    async def run(
        self, session_id: str, command: str, cwd: pathlib.Path, timeout: float
    ) -> Job:
        """Run a command to completion or until a timeout, then clean it up.

        Args:
            session_id: Session that owns the job.
            command: Shell command to run.
            cwd: Working directory for the process.
            timeout: Foreground runtime limit in seconds.

        Returns:
            The finished job, with ``timed_out`` set when the timeout was hit.
        """
        job = await self.start(session_id, command, cwd)
        try:
            await asyncio.wait_for(asyncio.shield(job.process.wait()), timeout)
        except TimeoutError:
            job.timed_out = True
            await self._terminate(job)
        if job.drain_task is not None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(job.drain_task), timeout=5)
        self._remove(session_id, job.id)
        return job

    def jobs(self, session_id: str) -> list[Job]:
        """Return a session's jobs, most recently started first."""
        return sorted(
            self._sessions.get(session_id, {}).values(),
            key=lambda job: job.started_at,
            reverse=True,
        )

    def get(self, session_id: str, job_id: str) -> Job | None:
        """Return a session's job by id, or ``None`` when unknown."""
        return self._sessions.get(session_id, {}).get(job_id)

    async def kill(self, session_id: str, job_id: str) -> Job | None:
        """Kill a running job and return it, or ``None`` when unknown."""
        job = self.get(session_id, job_id)
        if job is None:
            return None
        if job.status == "running":
            await self._terminate(job)
        return job

    async def kill_session(self, session_id: str) -> None:
        """Kill every running job for a session and forget its jobs."""
        jobs = self._sessions.pop(session_id, {})
        for job in jobs.values():
            if job.status == "running":
                await self._terminate(job)
        for job in jobs.values():
            if job.drain_task is not None:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(
                        asyncio.shield(job.drain_task), timeout=5
                    )

    async def shutdown(self) -> None:
        """Kill all jobs for all sessions."""
        for session_id in list(self._sessions):
            await self.kill_session(session_id)

    def output_text(self, job: Job, max_chars: int) -> str:
        """Return the job's output decoded as text, keeping only the tail.

        Args:
            job: Job whose buffered output should be read.
            max_chars: Maximum number of characters to return.

        Returns:
            The tail of the output, prefixed with ``[truncated]`` when it was
            shortened.
        """
        text = bytes(job.output).decode("utf-8", errors="replace")
        if len(text) > max_chars:
            return "[truncated]\n" + text[-max_chars:]
        return text

    def _remove(self, session_id: str, job_id: str) -> None:
        """Drop a finished foreground job from its session table."""
        jobs = self._sessions.get(session_id)
        if jobs is None:
            return
        jobs.pop(job_id, None)
        if not jobs:
            self._sessions.pop(session_id, None)


_manager: JobManager | None = None


def get_job_manager() -> JobManager:
    """Return the process-wide job manager, creating it on first use."""
    global _manager
    if _manager is None:
        _manager = JobManager()
    return _manager


def reset_job_manager() -> None:
    """Discard the process-wide job manager so the next call rebuilds it."""
    global _manager
    _manager = None


def make_terminal_tools(
    manager: JobManager,
    session_id: str,
    project_root: str,
    allowed_roots: list[pathlib.Path],
):
    """Build the terminal tool callables bound to one session.

    Args:
        manager: Job manager shared by the session.
        session_id: Session that owns started jobs.
        project_root: Root used to resolve relative working directories.
        allowed_roots: Additional directories a working directory may use.

    Returns:
        Mapping of tool names to async callables for pydantic-ai.
    """
    root = pathlib.Path(project_root).expanduser().resolve()

    def _resolve_cwd(cwd: str | None) -> pathlib.Path:
        """Resolve a tool working directory against the allowed roots."""
        from agentbox_harness.tools.paths import resolve_project_path

        return resolve_project_path(
            str(cwd or ""), str(root), [str(path) for path in allowed_roots]
        )

    async def run_command(
        command: str,
        cwd: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        background: bool = False,
    ) -> str:
        """Run a shell command in the project workspace.

        Args:
            command: Shell command to execute.
            cwd: Working directory relative to the project root.
            timeout: Maximum foreground runtime in seconds, capped internally.
            background: Start the command as a job and return immediately.

        Returns:
            Human-readable status and captured output. Failures are returned as text
            prefixed with ``Command failed:`` rather than raised.
        """
        text = (command or "").strip()
        if not text:
            return "Command failed: command must not be empty."
        try:
            workdir = _resolve_cwd(cwd)
        except ValueError as exc:
            return f"Command failed: {exc}"
        if background:
            # Start a job whose output is drained in the background; the model
            # polls it later with get_job_output.
            try:
                job = await manager.start(session_id, text, workdir)
            except (OSError, RuntimeError) as exc:
                return f"Command failed: {exc}"
            return (
                f"Started job {job.id} (pid {job.process.pid}): {text}\n"
                f'Use get_job_output("{job.id}") to read output.'
            )
        # Foreground runs are clamped to the supported timeout range.
        limit = max(1, min(MAX_TIMEOUT, int(timeout)))
        try:
            job = await manager.run(session_id, text, workdir, limit)
        except (OSError, RuntimeError) as exc:
            return f"Command failed: {exc}"
        duration = (job.ended_at or time.monotonic()) - job.started_at
        status = (
            f"timed out after {limit}s"
            if job.timed_out
            else f"exit code {job.exit_code}"
        )
        lines = [
            f"Command: {text}",
            f"Status: {status}",
            f"Duration: {duration:.2f}s",
        ]
        if job.truncated:
            lines.append("Output was truncated.")
        lines.append("Output:")
        lines.append(manager.output_text(job, MAX_OUTPUT_CHARS) or "(no output)")
        return "\n".join(lines)

    async def list_jobs() -> str:
        """List this session's jobs with status, pid, age, and command."""
        jobs = manager.jobs(session_id)
        if not jobs:
            return "No jobs."
        lines = ["Jobs:"]
        for job in jobs:
            age = (job.ended_at or time.monotonic()) - job.started_at
            exit_text = "" if job.exit_code is None else f" exit={job.exit_code}"
            command = job.command
            if len(command) > 120:
                command = command[:117] + "..."
            lines.append(
                f"- {job.id} {job.status}{exit_text} "
                f"pid={job.process.pid} age={age:.1f}s command={command}"
            )
        return "\n".join(lines)

    async def get_job_output(
        job_id: str, max_chars: int = DEFAULT_TAIL_CHARS
    ) -> str:
        """Return the most recent output from a background job.

        Args:
            job_id: Job id returned by ``run_command`` with ``background=true``.
            max_chars: Maximum number of trailing characters to return.

        Returns:
            Job status and output, or a not-found message.
        """
        job = manager.get(session_id, job_id)
        if job is None:
            return f"Job {job_id} not found."
        limit = max(100, min(MAX_TAIL_CHARS, int(max_chars)))
        status = job.status
        if job.exit_code is not None:
            status += f" (exit {job.exit_code})"
        lines = [f"Job {job.id}: {status}"]
        if job.truncated:
            lines.append("Output was truncated.")
        lines.append(manager.output_text(job, limit) or "(no output)")
        return "\n".join(lines)

    async def kill_job(job_id: str) -> str:
        """Stop a running background job.

        Args:
            job_id: Job id returned by ``run_command`` with ``background=true``.

        Returns:
            A confirmation, or a message when the job is missing or already
            finished.
        """
        job = manager.get(session_id, job_id)
        if job is None:
            return f"Job {job_id} not found."
        if job.status != "running":
            return f"Job {job.id} is already {job.status}."
        await manager.kill(session_id, job_id)
        return f"Killed job {job.id}."

    return {
        "run_command": run_command,
        "list_jobs": list_jobs,
        "get_job_output": get_job_output,
        "kill_job": kill_job,
    }
