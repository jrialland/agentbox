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
    if os.name == "nt":
        shell = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
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
        assert job.process.stdout is not None
        try:
            while True:
                chunk = await job.process.stdout.read(65536)
                if not chunk:
                    break
                job.output.extend(chunk)
                if len(job.output) > self._output_limit:
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
        return sorted(
            self._sessions.get(session_id, {}).values(),
            key=lambda job: job.started_at,
            reverse=True,
        )

    def get(self, session_id: str, job_id: str) -> Job | None:
        return self._sessions.get(session_id, {}).get(job_id)

    async def kill(self, session_id: str, job_id: str) -> Job | None:
        job = self.get(session_id, job_id)
        if job is None:
            return None
        if job.status == "running":
            await self._terminate(job)
        return job

    async def kill_session(self, session_id: str) -> None:
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
        for session_id in list(self._sessions):
            await self.kill_session(session_id)

    def output_text(self, job: Job, max_chars: int) -> str:
        text = bytes(job.output).decode("utf-8", errors="replace")
        if len(text) > max_chars:
            return "[truncated]\n" + text[-max_chars:]
        return text

    def _remove(self, session_id: str, job_id: str) -> None:
        jobs = self._sessions.get(session_id)
        if jobs is None:
            return
        jobs.pop(job_id, None)
        if not jobs:
            self._sessions.pop(session_id, None)


_manager: JobManager | None = None


def get_job_manager() -> JobManager:
    global _manager
    if _manager is None:
        _manager = JobManager()
    return _manager


def reset_job_manager() -> None:
    global _manager
    _manager = None


def make_terminal_tools(
    manager: JobManager,
    session_id: str,
    project_root: str,
    allowed_roots: list[pathlib.Path],
):
    root = pathlib.Path(project_root).expanduser().resolve()

    def _resolve_cwd(cwd: str | None) -> pathlib.Path:
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
        text = (command or "").strip()
        if not text:
            return "Command failed: command must not be empty."
        try:
            workdir = _resolve_cwd(cwd)
        except ValueError as exc:
            return f"Command failed: {exc}"
        if background:
            try:
                job = await manager.start(session_id, text, workdir)
            except (OSError, RuntimeError) as exc:
                return f"Command failed: {exc}"
            return (
                f"Started job {job.id} (pid {job.process.pid}): {text}\n"
                f'Use get_job_output("{job.id}") to read output.'
            )
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
