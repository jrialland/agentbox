"""Run Agentbox terminal jobs through an ACP client's terminal capability.

This backs the terminal tools when the connected ACP client advertises terminal
support: commands are created on the client, their output and exit status are
polled through ACP, and results are translated into the terminal tool's plain
text format.
"""

from __future__ import annotations

import asyncio
import contextlib
import pathlib
import time
from dataclasses import dataclass, field

from agentbox_harness.tools.paths import resolve_project_path
from agentbox_harness.tools.terminal import (
    DEFAULT_TAIL_CHARS,
    DEFAULT_TIMEOUT,
    JOB_OUTPUT_LIMIT,
    MAX_OUTPUT_CHARS,
    MAX_TAIL_CHARS,
    MAX_TIMEOUT,
    shell_command,
)


def _capped(text: str, limit: int) -> str:
    return f"[truncated]\n{text[-limit:]}" if len(text) > limit else text


@dataclass
class AcpTerminalJob:
    """Bookkeeping for one command running on the ACP client terminal."""

    terminal_id: str
    command: str
    cwd: pathlib.Path
    started_at: float = field(default_factory=time.monotonic)
    status: str = "running"
    exit_code: int | None = None
    signal: str | None = None
    output: str = ""
    truncated: bool = False
    timed_out: bool = False
    released: bool = False


class AcpTerminalTracker:
    """Track and translate ACP client terminal jobs for the terminal tools."""

    def __init__(
        self,
        client,
        session_id: str,
        project_root: str,
        extra_roots: list[str],
    ):
        self._client = client
        self._session_id = session_id
        self._project_root = project_root
        self._extra_roots = extra_roots
        self._jobs: dict[str, AcpTerminalJob] = {}

    def _resolve_cwd(self, cwd: str | None) -> pathlib.Path:
        return resolve_project_path(
            str(cwd or ""), self._project_root, self._extra_roots
        )

    async def run_command(
        self,
        command: str,
        cwd: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        background: bool = False,
    ) -> str:
        """Create a terminal on the ACP client and run a command.

        Args:
            command: Shell command line to execute.
            cwd: Working directory, resolved inside the session sandbox.
            timeout: Seconds to wait for exit when running in the foreground.
            background: Return as soon as the terminal is created instead of
                waiting for the command to exit.

        Returns:
            A plain-text result describing the job status, duration, and output.
        """
        text = (command or "").strip()
        if not text:
            return "Command failed: command must not be empty."
        try:
            workdir = self._resolve_cwd(cwd)
        except ValueError as exc:
            return f"Command failed: {exc}"
        parts = shell_command(text)
        try:
            created = await self._client.create_terminal(
                self._session_id,
                command=parts[0],
                args=parts[1:],
                cwd=str(workdir),
                output_byte_limit=JOB_OUTPUT_LIMIT,
            )
        except Exception as exc:
            return f"Command failed: {exc}"

        job = AcpTerminalJob(created.terminal_id, text, workdir)
        self._jobs[job.terminal_id] = job
        if background:
            return (
                f"Started job {job.terminal_id}: {text}\n"
                f'Use get_job_output("{job.terminal_id}") to read output.'
            )

        limit = max(1, min(MAX_TIMEOUT, int(timeout)))
        try:
            exit_response = await asyncio.wait_for(
                self._client.wait_for_terminal_exit(
                    self._session_id, job.terminal_id
                ),
                timeout=limit,
            )
        except TimeoutError:
            # A foreground timeout kills the client terminal, then refreshes and
            # releases it so no resources linger before reporting the timeout.
            job.timed_out = True
            with contextlib.suppress(Exception):
                await self._client.kill_terminal(self._session_id, job.terminal_id)
            await self._refresh(job)
            await self._release(job)
            job.status = "killed"
            duration = time.monotonic() - job.started_at
            lines = [
                f"Command: {text}",
                f"Status: timed out after {limit}s",
                f"Duration: {duration:.2f}s",
            ]
            if job.truncated:
                lines.append("Output was truncated.")
            lines.append("Output:")
            lines.append(_capped(job.output, MAX_OUTPUT_CHARS) or "(no output)")
            return "\n".join(lines)

        job.exit_code = exit_response.exit_code
        job.signal = exit_response.signal
        await self._refresh(job)
        await self._release(job)
        # Translate the ACP exit status into tool status: exit code 0 with no
        # signal is success, anything else is a failure.
        if job.exit_code == 0 and job.signal is None:
            job.status = "completed"
        else:
            job.status = "failed"
        duration = time.monotonic() - job.started_at
        status = (
            f"exit code {job.exit_code}"
            if job.exit_code is not None
            else f"signal {job.signal}"
        )
        lines = [
            f"Command: {text}",
            f"Status: {status}",
            f"Duration: {duration:.2f}s",
        ]
        if job.truncated:
            lines.append("Output was truncated.")
        lines.append("Output:")
        lines.append(_capped(job.output, MAX_OUTPUT_CHARS) or "(no output)")
        return "\n".join(lines)

    async def _refresh(self, job: AcpTerminalJob) -> None:
        if job.released:
            return
        try:
            response = await self._client.terminal_output(
                self._session_id, job.terminal_id
            )
        except Exception as exc:
            if job.status == "running":
                job.status = "failed"
                job.signal = str(exc)
            return
        job.output = response.output
        job.truncated = response.truncated
        if response.exit_status is not None:
            job.exit_code = response.exit_status.exit_code
            job.signal = response.exit_status.signal
            if job.status == "running":
                job.status = (
                    "completed"
                    if job.exit_code == 0 and job.signal is None
                    else "failed"
                )

    async def _release(self, job: AcpTerminalJob) -> None:
        if job.released:
            return
        job.released = True
        with contextlib.suppress(Exception):
            await self._client.release_terminal(self._session_id, job.terminal_id)

    async def list_jobs(self) -> str:
        """List tracked terminal jobs, refreshing each from the client.

        Returns:
            A plain-text job summary, newest first, or ``"No jobs."``.
        """
        jobs = list(self._jobs.values())
        if not jobs:
            return "No jobs."
        for job in jobs:
            await self._refresh(job)
        lines = ["Jobs:"]
        for job in sorted(jobs, key=lambda item: item.started_at, reverse=True):
            age = time.monotonic() - job.started_at
            exit_text = "" if job.exit_code is None else f" exit={job.exit_code}"
            command = job.command
            if len(command) > 120:
                command = command[:117] + "..."
            lines.append(
                f"- {job.terminal_id} {job.status}{exit_text} "
                f"age={age:.1f}s command={command}"
            )
        return "\n".join(lines)

    async def get_job_output(
        self, job_id: str, max_chars: int = DEFAULT_TAIL_CHARS
    ) -> str:
        """Return a job's status and the trailing part of its output.

        Args:
            job_id: Terminal id of the job to read.
            max_chars: Maximum trailing characters to include, clamped to the
                supported tail range.

        Returns:
            A plain-text status and output excerpt, or a not-found message.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return f"Job {job_id} not found."
        await self._refresh(job)
        limit = max(100, min(MAX_TAIL_CHARS, int(max_chars)))
        status = job.status
        if job.exit_code is not None:
            status += f" (exit {job.exit_code})"
        lines = [f"Job {job.terminal_id}: {status}"]
        if job.truncated:
            lines.append("Output was truncated.")
        lines.append(_capped(job.output, limit) or "(no output)")
        return "\n".join(lines)

    async def kill_job(self, job_id: str) -> str:
        """Kill a running job on the client and release its terminal.

        Args:
            job_id: Terminal id of the job to kill.

        Returns:
            A plain-text confirmation, an already-finished message, or a
            not-found message.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return f"Job {job_id} not found."
        await self._refresh(job)
        if job.status != "running":
            return f"Job {job.terminal_id} is already {job.status}."
        with contextlib.suppress(Exception):
            await self._client.kill_terminal(self._session_id, job.terminal_id)
        job.status = "killed"
        await self._release(job)
        return f"Killed job {job.terminal_id}."

    async def close(self) -> None:
        """Kill any running jobs and release every tracked terminal."""
        # Iterate over a snapshot so mutating job state does not affect the loop,
        # and release each terminal only after it has been killed.
        for job in list(self._jobs.values()):
            if job.status == "running":
                with contextlib.suppress(Exception):
                    await self._client.kill_terminal(
                        self._session_id, job.terminal_id
                    )
                job.status = "killed"
            await self._release(job)
        self._jobs.clear()
