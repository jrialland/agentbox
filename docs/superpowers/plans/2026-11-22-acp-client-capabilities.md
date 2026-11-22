# ACP Client Capabilities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the complete ACP v1 client capability surface: `fs/read_text_file`, `fs/write_text_file`, and every `terminal/*` method, with capability gating and server-side fallback.

**Architecture:** The ACP adapter installs tool overrides on the existing `ToolRegistry`; the harness stays protocol-agnostic. Filesystem tools route through ACP read/write only when the client advertises the capability and the path is inside the project/extra roots. Terminal tools route through a per-session ACP terminal tracker. Non-ACP operations remain server-side.

**Tech Stack:** Python 3.11, `uv`, pydantic-ai, FastAPI, `acp` (`agent-client-protocol`), pytest/pytest-asyncio, Ruff, Ty.

## Global Constraints

- Implement every ACP-defined client method. Do not invent ACP methods for media, directory, mkdir, move, or delete.
- ACP file routing applies only to paths inside the project root plus extra roots. Outside paths use the original server-side tool.
- Override only tools already bound by the agent spec.
- Surface ACP client errors for routed paths; do not silently retry server-side.
- Preserve existing tool return strings and validation behavior where practical.
- Release all ACP terminals on ACP session close/delete.
- Python line length 100; run one package test directory per pytest invocation.
- Run Python commands from the repo root; frontend commands from `apps/web`.
- Before every commit, run `git status` and stage only the files listed in the current task. Do not use `git add -A` or stage unrelated working-tree changes.

---

## File Structure

- `packages/agentbox-harness/src/agentbox_harness/tools/registry.py` — raw callable access and override support.
- `packages/agentbox-harness/src/agentbox_harness/tools/filesystem.py` — public `apply_file_edit`.
- `packages/agentbox-harness/src/agentbox_harness/tools/terminal.py` — public `shell_command`.
- `packages/agentbox-api/src/agentbox_api/acp_terminals.py` — ACP terminal tracker and tool implementations.
- `packages/agentbox-api/src/agentbox_api/acp_client_tools.py` — ACP capabilities, filesystem wrappers, install function.
- `packages/agentbox-api/src/agentbox_api/acp_server.py` — capability capture, install/close per session.
- `packages/agentbox-providers/src/agentbox_providers/resolver.py` — test provider kinds for ACP E2E.
- `packages/agentbox-api/tests/test_acp_terminals.py` — terminal unit tests.
- `packages/agentbox-api/tests/test_acp_client_tools.py` — filesystem unit tests.
- `packages/agentbox-harness/tests/test_tool_registry.py` — registry raw/override tests.
- `packages/agentbox-api/tests/test_acp.py`, `test_acp_stdio.py` — adapter and stdio tests.

---

### Task 1: Harness registry and helper primitives

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/registry.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/filesystem.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/terminal.py`
- Test: `packages/agentbox-harness/tests/test_tool_registry.py`

**Interfaces:**
- Produces:
  - `ToolRegistry.get_native_raw(name: str) -> Callable | None`
  - `ToolRegistry.override_native(name: str, callable: Callable) -> bool`
  - `agentbox_harness.tools.filesystem.apply_file_edit(text, edit, newline) -> str`
  - `agentbox_harness.tools.terminal.shell_command(command: str) -> list[str]`

- [ ] **Step 1: Write the failing registry tests**

Append to `test_tool_registry.py`:

```python
def test_get_native_raw_returns_unwrapped_callable():
    async def original(path: str) -> str:
        return "raw"

    reg = ToolRegistry()
    reg.register_native("read_file", original)

    assert reg.get_native_raw("read_file") is original
    assert reg.get_native_raw("missing") is None


async def test_override_native_preserves_flags_and_runs_hooks_once():
    calls: list[str] = []

    async def hook(ctx):
        calls.append("hook")
        return "hooked"

    async def original(path: str) -> str:
        return "raw"

    async def replacement(path: str) -> str:
        return "new"

    reg = ToolRegistry(hooks=[hook])
    reg.register_native("read_file", original, required_flags=("read",))

    assert reg.override_native("read_file", replacement) is True
    assert reg.get_native_raw("read_file") is replacement
    assert reg.override_native("missing", replacement) is False

    tool = reg.select_tools(Mode(name="ask", flags={}), names={"read_file"})[0]
    assert await tool("a.txt") == "new\n\nhooked"
    assert calls == ["hook"]
```

- [ ] **Step 2: Run the registry tests and verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_tool_registry.py -q`

Expected: FAIL because `get_native_raw` and `override_native` do not exist.

- [ ] **Step 3: Add raw/override support to `ToolRegistry`**

Replace `_Entry` and `register_native` with the following while preserving the existing hook behavior:

```python
@dataclass
class _Entry:
    callable: Callable
    raw: Callable
    required_flags: tuple[str, ...] = ()


class ToolRegistry:
    def __init__(self, hooks: list[ToolHook] | None = None, root=None) -> None:
        self._native: dict[str, _Entry] = {}
        self._hooks = list(hooks or [])
        self._root = root

    def register_native(
        self,
        name: str,
        callable: Callable,
        required_flags: tuple[str, ...] = (),
    ) -> None:
        raw = callable
        fn = callable
        if self._hooks:
            original = callable

            @functools.wraps(original)
            async def wrapped(*args, **kwargs):
                result = await original(*args, **kwargs)
                try:
                    bound = inspect.signature(original).bind(*args, **kwargs)
                    call_args = dict(bound.arguments)
                except TypeError:
                    call_args = dict(kwargs)
                extras: list[str] = []
                for hook in self._hooks:
                    try:
                        extra = await hook(
                            ToolHookContext(
                                tool_name=name,
                                args=call_args,
                                root=self._root,
                                result=result,
                            )
                        )
                    except Exception:
                        logger.exception("tool hook failed tool={}", name)
                        continue
                    if extra:
                        extras.append(extra)
                if extras and isinstance(result, str):
                    return "\n\n".join([result, *extras])
                return result

            fn = wrapped
        self._native[name] = _Entry(fn, raw, required_flags)

    def get_native_raw(self, name: str) -> Callable | None:
        entry = self._native.get(name)
        return entry.raw if entry is not None else None

    def override_native(self, name: str, callable: Callable) -> bool:
        entry = self._native.get(name)
        if entry is None:
            return False
        self.register_native(name, callable, required_flags=entry.required_flags)
        return True

    def select_tools(
        self, mode: Mode, names: set[str] | None = None
    ) -> list[Callable]:
        result = []
        for name, entry in self._native.items():
            if names is not None and name not in names:
                continue
            if all(mode.allows(f) for f in entry.required_flags):
                result.append(entry.callable)
        return result
```

- [ ] **Step 4: Rename and expose the filesystem helper**

In `filesystem.py`, rename `_apply_edit` to `apply_file_edit` and change the call inside `edit_file`:

```python
updated = apply_file_edit(updated, edit, newline)
```

- [ ] **Step 5: Rename and expose the terminal shell helper**

In `terminal.py`, rename `_shell_command` to `shell_command` and change `JobManager._spawn`:

```python
*shell_command(command),
```

- [ ] **Step 6: Run the harness tests**

Run: `uv run pytest packages/agentbox-harness -q`

Expected: PASS. The existing filesystem and terminal tests exercise the renamed helpers.

- [ ] **Step 7: Commit**

```powershell
git add packages/agentbox-harness/src/agentbox_harness/tools/registry.py packages/agentbox-harness/src/agentbox_harness/tools/filesystem.py packages/agentbox-harness/src/agentbox_harness/tools/terminal.py packages/agentbox-harness/tests/test_tool_registry.py
git commit -m "refactor(harness): expose tool registry and helper primitives"
```

---

### Task 2: ACP terminal tracker and terminal tools

**Files:**
- Create: `packages/agentbox-api/src/agentbox_api/acp_terminals.py`
- Create: `packages/agentbox-api/tests/test_acp_terminals.py`

**Interfaces:**
- Consumes: `shell_command`, `resolve_project_path`, ACP `Client`.
- Produces:
  - `AcpTerminalJob`
  - `AcpTerminalTracker(client, session_id, project_root, extra_roots)`
  - Async methods `run_command`, `list_jobs`, `get_job_output`, `kill_job`, `close`.

- [ ] **Step 1: Write the failing terminal tests**

Create `test_acp_terminals.py`:

```python
import asyncio

from acp import schema as s

from agentbox_api.acp_terminals import AcpTerminalTracker


class FakeClient:
    def __init__(self, exit_code=0, output="hello\n", wait=True):
        self.calls = []
        self.exit_code = exit_code
        self.output = output
        self.wait = wait

    async def create_terminal(self, session_id, command, args=None, cwd=None, **kwargs):
        self.calls.append(("create", session_id, command, args, cwd))
        return s.CreateTerminalResponse(terminal_id="t1")

    async def wait_for_terminal_exit(self, session_id, terminal_id, **kwargs):
        self.calls.append(("wait", session_id, terminal_id))
        if self.wait:
            return s.WaitForTerminalExitResponse(exit_code=self.exit_code)
        await asyncio.sleep(2)
        return s.WaitForTerminalExitResponse(exit_code=self.exit_code)

    async def terminal_output(self, session_id, terminal_id, **kwargs):
        self.calls.append(("output", session_id, terminal_id))
        return s.TerminalOutputResponse(output=self.output, truncated=False)

    async def kill_terminal(self, session_id, terminal_id, **kwargs):
        self.calls.append(("kill", session_id, terminal_id))

    async def release_terminal(self, session_id, terminal_id, **kwargs):
        self.calls.append(("release", session_id, terminal_id))


def _tracker(tmp_path, client):
    from agentbox_api.acp_terminals import AcpTerminalTracker

    return AcpTerminalTracker(client, "s1", str(tmp_path), [])


async def test_foreground_command_uses_terminal_and_releases(tmp_path):
    client = FakeClient()
    tracker = _tracker(tmp_path, client)
    result = await tracker.run_command("echo hi")
    assert "exit code 0" in result
    assert "hello" in result
    assert [call[0] for call in client.calls] == ["create", "wait", "output", "release"]


async def test_background_list_output_and_kill(tmp_path):
    client = FakeClient()
    tracker = _tracker(tmp_path, client)
    started = await tracker.run_command("echo hi", background=True)
    assert "Started job t1" in started
    assert "t1" in await tracker.list_jobs()
    output = await tracker.get_job_output("t1")
    assert "hello" in output
    assert await tracker.kill_job("t1") == "Killed job t1."
    assert "kill" in [call[0] for call in client.calls]
    assert "release" in [call[0] for call in client.calls]


async def test_timeout_kills_and_releases(tmp_path):
    client = FakeClient(wait=False)
    tracker = _tracker(tmp_path, client)
    result = await tracker.run_command("sleep 10", timeout=1)
    assert "timed out after 1s" in result
    assert "kill" in [call[0] for call in client.calls]
    assert "release" in [call[0] for call in client.calls]


async def test_bad_cwd_and_empty_command_do_not_create_terminal(tmp_path):
    client = FakeClient()
    tracker = _tracker(tmp_path, client)
    assert "must not be empty" in await tracker.run_command("  ")
    assert "escapes" in await tracker.run_command("echo hi", cwd="../escape")
    assert client.calls == []


async def test_close_releases_background_jobs(tmp_path):
    client = FakeClient()
    tracker = _tracker(tmp_path, client)
    await tracker.run_command("echo hi", background=True)
    await tracker.close()
    assert "release" in [call[0] for call in client.calls]
```

- [ ] **Step 2: Run the terminal tests and verify they fail**

Run: `uv run pytest packages/agentbox-api/tests/test_acp_terminals.py -q`

Expected: FAIL because `agentbox_api.acp_terminals` does not exist.

- [ ] **Step 3: Implement `acp_terminals.py`**

```python
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
    def __init__(self, client, session_id: str, project_root: str, extra_roots: list[str]):
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
        lines = [f"Command: {text}", f"Status: {status}", f"Duration: {duration:.2f}s"]
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
        for job in list(self._jobs.values()):
            if job.status == "running":
                with contextlib.suppress(Exception):
                    await self._client.kill_terminal(
                        self._session_id, job.terminal_id
                    )
                job.status = "killed"
            await self._release(job)
        self._jobs.clear()
```

- [ ] **Step 4: Run the terminal tests**

Run: `uv run pytest packages/agentbox-api/tests/test_acp_terminals.py -q`

Expected: PASS. The timeout test takes about one second.

- [ ] **Step 5: Run ruff**

Run: `uv run ruff check packages/agentbox-api/src/agentbox_api/acp_terminals.py packages/agentbox-api/tests/test_acp_terminals.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add packages/agentbox-api/src/agentbox_api/acp_terminals.py packages/agentbox-api/tests/test_acp_terminals.py
git commit -m "feat(api): add ACP terminal tool tracker"
```

---

### Task 3: ACP capabilities and filesystem routing

**Files:**
- Create: `packages/agentbox-api/src/agentbox_api/acp_client_tools.py`
- Create: `packages/agentbox-api/tests/test_acp_client_tools.py`

**Interfaces:**
- Consumes: `ToolRegistry.get_native_raw`, `ToolRegistry.override_native`, `apply_file_edit`, `resolve_project_path`, `AcpTerminalTracker`.
- Produces:
  - `AcpClientCapabilities.from_sdk(caps)`.
  - `AcpClientTools.close()`.
  - `install_acp_client_tools(registry, spec, tools)`.

- [ ] **Step 1: Write the failing filesystem tests**

Create `test_acp_client_tools.py`:

```python
import pathlib

import pytest
from acp import schema as s

from agentbox_api.acp_client_tools import (
    AcpClientCapabilities,
    AcpClientTools,
    install_acp_client_tools,
)
from agentbox_harness.spec import AgentSpec, Mode, ModelBinding, NativeToolBinding
from agentbox_harness.tools.filesystem import FileEdit
from agentbox_harness.tools.registry import ToolRegistry


class FakeClient:
    def __init__(self):
        self.reads = []
        self.writes = []

    async def read_text_file(self, session_id, path, line=None, limit=None, **kwargs):
        self.reads.append((session_id, path))
        return s.ReadTextFileResponse(content=pathlib.Path(path).read_text())

    async def write_text_file(self, session_id, path, content, **kwargs):
        self.writes.append((session_id, path, content))
        pathlib.Path(path).write_text(content)
        return None


async def server_read(path, head=None, tail=None):
    return "server read"


async def server_write(path, content):
    return "server write"


async def server_edit(path, edits, dry_run=False):
    return "server edit"


async def server_append(path, content):
    return "server append"


async def server_copy(source, destination):
    return "server copy"


async def server_read_multiple(paths):
    return "server multiple"


def _registry():
    reg = ToolRegistry()
    reg.register_native("read_text_file", server_read, required_flags=("read",))
    reg.register_native("read_file", server_read, required_flags=("read",))
    reg.register_native(
        "read_multiple_files", server_read_multiple, required_flags=("read",)
    )
    reg.register_native("write_file", server_write, required_flags=("write",))
    reg.register_native("append_file", server_append, required_flags=("write",))
    reg.register_native("edit_file", server_edit, required_flags=("write",))
    reg.register_native("copy_file", server_copy, required_flags=("write",))
    return reg


def _spec(names):
    return AgentSpec(
        name="coder",
        description="d",
        instructions="i",
        tool_bindings=[NativeToolBinding(name=name) for name in names],
        model_binding=ModelBinding(model="test", provider="test"),
    )


def _tools(tmp_path, client, caps):
    return AcpClientTools(
        client=client,
        session_id="s1",
        project_root=str(tmp_path),
        extra_roots=[],
        capabilities=caps,
    )


def _tool(reg, name):
    return reg.select_tools(Mode(name="agent", flags={"write": True}), names={name})[0]


async def test_no_capabilities_leaves_server_tools(tmp_path):
    reg = _registry()
    install_acp_client_tools(
        reg,
        _spec(["read_text_file", "write_file"]),
        _tools(tmp_path, FakeClient(), AcpClientCapabilities()),
    )
    assert await _tool(reg, "read_text_file")("a.txt") == "server read"
    assert await _tool(reg, "write_file")("a.txt", "x") == "server write"


async def test_read_routes_head_and_tail(tmp_path):
    (tmp_path / "a.txt").write_text("a\nb\nc\n")
    reg = _registry()
    client = FakeClient()
    install_acp_client_tools(
        reg,
        _spec(["read_text_file"]),
        _tools(tmp_path, client, AcpClientCapabilities(read_text_file=True)),
    )
    tool = _tool(reg, "read_text_file")
    assert await tool("a.txt", head=2) == "a\nb"
    assert await tool("a.txt", tail=2) == "b\nc"
    assert await tool("a.txt") == "a\nb\nc\n"
    assert client.reads


async def test_write_and_composed_tools_use_client(tmp_path):
    (tmp_path / "a.txt").write_text("old")
    reg = _registry()
    client = FakeClient()
    install_acp_client_tools(
        reg,
        _spec(["write_file", "append_file", "edit_file", "copy_file"]),
        _tools(
            tmp_path,
            client,
            AcpClientCapabilities(read_text_file=True, write_text_file=True),
        ),
    )

    assert await _tool(reg, "write_file")("b.txt", "new") == "Wrote 3 bytes to b.txt"
    assert await _tool(reg, "append_file")("a.txt", "!") == "Appended 1 bytes to a.txt"
    assert (tmp_path / "a.txt").read_text() == "old!"

    assert (
        await _tool(reg, "edit_file")("a.txt", [FileEdit("old", "NEW")])
        == "Edited a.txt"
    )
    assert (tmp_path / "a.txt").read_text() == "NEW!"

    diff = await _tool(reg, "edit_file")("a.txt", [FileEdit("NEW", "NEWER")], dry_run=True)
    assert "+NEWER" in diff
    assert (tmp_path / "a.txt").read_text() == "NEW!"

    assert (
        await _tool(reg, "copy_file")("a.txt", "c.txt")
        == "Copied a.txt to c.txt"
    )
    assert (tmp_path / "c.txt").read_text() == "NEW!"
    assert client.writes


async def test_outside_root_falls_back_to_server_tool(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside")
    reg = _registry()
    client = FakeClient()
    install_acp_client_tools(
        reg,
        _spec(["read_text_file"]),
        _tools(tmp_path, client, AcpClientCapabilities(read_text_file=True)),
    )
    assert await _tool(reg, "read_text_file")(str(outside)) == "server read"
    assert client.reads == []


async def test_client_error_is_surfaced(tmp_path):
    class BrokenClient(FakeClient):
        async def read_text_file(self, *args, **kwargs):
            raise RuntimeError("client failed")

    reg = _registry()
    install_acp_client_tools(
        reg,
        _spec(["read_text_file"]),
        _tools(tmp_path, BrokenClient(), AcpClientCapabilities(read_text_file=True)),
    )
    with pytest.raises(RuntimeError, match="client failed"):
        await _tool(reg, "read_text_file")("a.txt")
```

- [ ] **Step 2: Run the filesystem tests and verify they fail**

Run: `uv run pytest packages/agentbox-api/tests/test_acp_client_tools.py -q`

Expected: FAIL because `agentbox_api.acp_client_tools` does not exist.

- [ ] **Step 3: Implement `acp_client_tools.py`**

Create the module with capability parsing, filesystem wrappers, install, and terminal install:

```python
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
    read_text_file: bool = False
    write_text_file: bool = False
    terminal: bool = False

    @classmethod
    def from_sdk(cls, caps: Any) -> AcpClientCapabilities:
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
    client: acp.Client
    session_id: str
    project_root: str
    extra_roots: list[str]
    capabilities: AcpClientCapabilities
    terminals: AcpTerminalTracker | None = None

    async def close(self) -> None:
        if self.terminals is not None:
            await self.terminals.close()


def _resolve(path: str, tools: AcpClientTools) -> pathlib.Path | None:
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

    if tools.capabilities.terminal and any(name in names for name in TERMINAL_TOOL_NAMES):
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
```

- [ ] **Step 4: Run the filesystem tests**

Run: `uv run pytest packages/agentbox-api/tests/test_acp_client_tools.py -q`

Expected: PASS.

- [ ] **Step 5: Run ruff**

Run: `uv run ruff check packages/agentbox-api/src/agentbox_api/acp_client_tools.py packages/agentbox-api/tests/test_acp_client_tools.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add packages/agentbox-api/src/agentbox_api/acp_client_tools.py packages/agentbox-api/tests/test_acp_client_tools.py
git commit -m "feat(api): route filesystem tools through ACP client capabilities"
```

---

### Task 4: Wire ACP sessions, add test providers, and verify end to end

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/acp_server.py`
- Modify: `packages/agentbox-providers/src/agentbox_providers/resolver.py`
- Modify: `packages/agentbox-api/tests/test_acp_stdio.py`
- Modify: `packages/agentbox-api/tests/test_acp.py`

**Interfaces:**
- Consumes: `AcpClientCapabilities`, `AcpClientTools`, `install_acp_client_tools`.
- Produces: capability-aware ACP sessions and test provider kinds `test_acp_fs`, `test_acp_terminal`.

- [ ] **Step 1: Add the test provider kinds**

In `resolver.py`, add after `test_tool`:

```python
    if kind == "test_acp_fs":
        from pydantic_ai.models.function import DeltaToolCall, FunctionModel

        async def fs_stream(messages, info):
            has_tool_result = any(
                getattr(part, "part_kind", "") == "tool-return"
                for message in messages
                for part in message.parts
            )
            if not has_tool_result:
                yield {
                    0: DeltaToolCall(
                        name="read_text_file",
                        json_args='{"path": "hello.txt"}',
                        tool_call_id="fs-call",
                    )
                }
                return
            yield "FS done"

        return FunctionModel(
            stream_function=fs_stream, model_name=model_name, profile=profile
        )
    if kind == "test_acp_terminal":
        from pydantic_ai.models.function import DeltaToolCall, FunctionModel

        async def terminal_stream(messages, info):
            has_tool_result = any(
                getattr(part, "part_kind", "") == "tool-return"
                for message in messages
                for part in message.parts
            )
            if not has_tool_result:
                yield {
                    0: DeltaToolCall(
                        name="run_command",
                        json_args='{"command": "echo hi"}',
                        tool_call_id="terminal-call",
                    )
                }
                return
            yield "Terminal done"

        return FunctionModel(
            stream_function=terminal_stream, model_name=model_name, profile=profile
        )
```

- [ ] **Step 2: Add client capability methods to the stdio test client**

Extend `CollectingClient` in `test_acp_stdio.py`:

```python
class CollectingClient(Client):
    def __init__(self):
        self.updates = []
        self.calls = []

    async def session_update(self, session_id, update, **kwargs):
        self.updates.append(update)

    async def request_permission(self, session_id, tool_call, options, **kwargs):
        return {"outcome": {"outcome": "cancelled"}}

    async def read_text_file(self, session_id, path, line=None, limit=None, **kwargs):
        self.calls.append(("read_text_file", session_id, path))
        return s.ReadTextFileResponse(content="client file content")

    async def write_text_file(self, session_id, path, content, **kwargs):
        self.calls.append(("write_text_file", session_id, path, content))
        return None

    async def create_terminal(self, session_id, command, args=None, cwd=None, **kwargs):
        self.calls.append(("create_terminal", session_id, command, args, cwd))
        return s.CreateTerminalResponse(terminal_id="term-1")

    async def wait_for_terminal_exit(self, session_id, terminal_id, **kwargs):
        self.calls.append(("wait_for_terminal_exit", session_id, terminal_id))
        return s.WaitForTerminalExitResponse(exit_code=0)

    async def terminal_output(self, session_id, terminal_id, **kwargs):
        self.calls.append(("terminal_output", session_id, terminal_id))
        return s.TerminalOutputResponse(
            output="client terminal output",
            truncated=False,
            exit_status=s.TerminalExitStatus(exit_code=0),
        )

    async def kill_terminal(self, session_id, terminal_id, **kwargs):
        self.calls.append(("kill_terminal", session_id, terminal_id))

    async def release_terminal(self, session_id, terminal_id, **kwargs):
        self.calls.append(("release_terminal", session_id, terminal_id))
```

- [ ] **Step 3: Add the two stdio capability tests**

Add to `test_acp_stdio.py`:

```python
async def test_acp_stdio_uses_client_filesystem(tmp_path):
    db_path = tmp_path / "acp-fs.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine, factory = create_engine_and_sessionmaker(url)
    await init_db(engine)
    async with factory() as db:
        db.add(Provider(id="prov", name="test", kind="test_acp_fs"))
        db.add(Model(id="m", provider_id="prov", name="test-model"))
        db.add(
            Agent(
                id="ag",
                name="acp-fs",
                description="",
                instructions="",
                model_id="m",
                tool_bindings='[{"name":"read_text_file"}]',
                mode_definitions='[{"name":"agent","flags":{"write":true}}]',
            )
        )
        await db.commit()
    await engine.dispose()

    client = CollectingClient()  # ty: ignore[abstract-class-instantiation]
    async with spawn_agent_process(
        client,
        sys.executable,
        "-m",
        "agentbox_api.acp_server",
        "--agent",
        "acp-fs",
        env={**os.environ, "DATABASE_URL": url},
        cwd=str(tmp_path),
    ) as (conn, _proc):
        await conn.initialize(
            protocol_version=PROTOCOL_VERSION,
            client_capabilities=s.ClientCapabilities(
                fs=s.FileSystemCapabilities(read_text_file=True, write_text_file=True)
            ),
        )
        session = await conn.new_session(cwd=str(tmp_path), mcp_servers=[])
        resp = await conn.prompt(
            session_id=session.session_id,
            prompt=[s.TextContentBlock(text="read")],
        )
        assert resp.stop_reason == "end_turn"
        assert any(call[0] == "read_text_file" for call in client.calls)


async def test_acp_stdio_uses_client_terminal(tmp_path):
    db_path = tmp_path / "acp-terminal.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine, factory = create_engine_and_sessionmaker(url)
    await init_db(engine)
    async with factory() as db:
        db.add(Provider(id="prov", name="test", kind="test_acp_terminal"))
        db.add(Model(id="m", provider_id="prov", name="test-model"))
        db.add(
            Agent(
                id="ag",
                name="acp-terminal",
                description="",
                instructions="",
                model_id="m",
                tool_bindings='[{"name":"run_command"}]',
                mode_definitions='[{"name":"agent","flags":{"write":true}}]',
            )
        )
        await db.commit()
    await engine.dispose()

    client = CollectingClient()  # ty: ignore[abstract-class-instantiation]
    async with spawn_agent_process(
        client,
        sys.executable,
        "-m",
        "agentbox_api.acp_server",
        "--agent",
        "acp-terminal",
        env={**os.environ, "DATABASE_URL": url},
        cwd=str(tmp_path),
    ) as (conn, _proc):
        await conn.initialize(
            protocol_version=PROTOCOL_VERSION,
            client_capabilities=s.ClientCapabilities(terminal=True),
        )
        session = await conn.new_session(cwd=str(tmp_path), mcp_servers=[])
        resp = await conn.prompt(
            session_id=session.session_id,
            prompt=[s.TextContentBlock(text="run")],
        )
        assert resp.stop_reason == "end_turn"
        assert any(call[0] == "create_terminal" for call in client.calls)
        assert any(call[0] == "release_terminal" for call in client.calls)
```

- [ ] **Step 4: Wire capabilities into `AcpSession` and the ACP agent**

In `acp_server.py`:

- Import `AcpClientCapabilities`, `AcpClientTools`, `install_acp_client_tools`.
- Add `client_tools: AcpClientTools | None = None` to `AcpSession`.
- In `AcpSession` constructor calls, pass `client_tools=client_tools`.
- In `AgentboxAcpAgent.__init__`, set `self._client_capabilities = AcpClientCapabilities()`.
- Add a read-only property:

```python
    @property
    def client_capabilities(self) -> AcpClientCapabilities:
        return self._client_capabilities
```

- In `initialize`, set `self._client_capabilities = AcpClientCapabilities.from_sdk(client_capabilities)`.
- In `new_session`, after `prepared = await prepare_agent(...)` and before constructing `AcpSession`:

```python
        client_tools = None
        if self._client is not None:
            client_tools = AcpClientTools(
                client=self._client,
                session_id=session_id,
                project_root=cwd,
                extra_roots=project.extra_roots if project is not None else [],
                capabilities=self._client_capabilities,
            )
            install_acp_client_tools(prepared.registry, prepared.spec, client_tools)
```

- In `_restore`, close any old state and install before storing the new `AcpSession`:

```python
        old = self._sessions.get(session_id)
        if old is not None and old.client_tools is not None:
            await old.client_tools.close()
        client_tools = None
        if self._client is not None:
            client_tools = AcpClientTools(
                client=self._client,
                session_id=session_id,
                project_root=project.path,
                extra_roots=project.extra_roots,
                capabilities=self._client_capabilities,
            )
            install_acp_client_tools(prepared.registry, prepared.spec, client_tools)
```

- In `close_session`, pop the session and close tools before cancelling the run:

```python
        sess = self._sessions.pop(session_id, None)
        if sess is not None and sess.client_tools is not None:
            await sess.client_tools.close()
        if sess is not None and sess.run is not None:
            sess.run.cancel()
```

- In `delete_session`, close tools before deleting data:

```python
        sess = self._sessions.pop(session_id, None)
        if sess is not None and sess.client_tools is not None:
            await sess.client_tools.close()
        await delete_session_data(self._factory, session_id)
        return s.DeleteSessionResponse()
```

- [ ] **Step 5: Add a capability assertion to `test_acp.py`**

Add near the lifecycle test:

```python
async def test_initialize_stores_client_capabilities():
    from agentbox_api.acp_client_tools import AcpClientCapabilities

    from agentbox_api.acp_server import AgentboxAcpAgent

    agent = AgentboxAcpAgent("acp-test", None, None)
    await agent.initialize(
        1,
        client_capabilities=s.ClientCapabilities(
            fs=s.FileSystemCapabilities(read_text_file=True, write_text_file=True),
            terminal=True,
        ),
    )
    assert agent.client_capabilities == AcpClientCapabilities(
        read_text_file=True, write_text_file=True, terminal=True
    )
```

- [ ] **Step 6: Run the focused tests**

Run:

```powershell
uv run pytest packages/agentbox-api/tests/test_acp_client_tools.py packages/agentbox-api/tests/test_acp_terminals.py -q
uv run pytest packages/agentbox-api/tests/test_acp.py -q
uv run pytest packages/agentbox-api/tests/test_acp_stdio.py -q
```

Expected: PASS.

- [ ] **Step 7: Run the full API package**

Run: `uv run pytest packages/agentbox-api -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add packages/agentbox-api/src/agentbox_api/acp_server.py packages/agentbox-providers/src/agentbox_providers/resolver.py packages/agentbox-api/tests/test_acp.py packages/agentbox-api/tests/test_acp_stdio.py
git commit -m "feat(api): wire ACP client fs and terminal capabilities"
```

---

### Task 5: Documentation, roadmap, and full verification

**Files:**
- Modify: `docs/ROADMAP.md`
- Modify: `docs/architecture/07-protocols.md`
- Modify: `docs/architecture/11-testing-and-observability.md`

**Interfaces:**
- Consumes: completed implementation.
- Produces: docs and roadmap reflecting ACP client capability support.

- [ ] **Step 1: Update the roadmap**

In `docs/ROADMAP.md`:

- Change the ACP row notes to:

```text
ACP v1 agent over stdio; full session lifecycle; image/audio/embedded + stdio MCP. Client `fs/read_text_file`, `fs/write_text_file`, and all `terminal/*` capabilities are implemented with server-side fallback.
```

- Remove the `D23` row from the deferred backlog.
- Add a sub-project history row:

```text
| 40 | ACP client capabilities (fs read/write + terminal) | `specs/2026-11-22-acp-client-capabilities-design.md` | `plans/2026-11-22-acp-client-capabilities.md` |
```

- [ ] **Step 2: Update the ACP protocol documentation**

In `docs/architecture/07-protocols.md`, add to the ACP section:

```text
- Client capabilities: when `fs.readTextFile` is advertised, `read_text_file`, `read_file`,
  and `read_multiple_files` use the client; when `fs.writeTextFile` is advertised,
  `write_file` uses the client. With both, `append_file`, `edit_file`, and `copy_file` are
  composed through client read/write. When `terminal` is advertised, all terminal tools use
  client terminals. Paths outside the project/extra roots and clients without the
  capability use the server-side tools. ACP terminals are released on session close/delete.
- ACP defines no client methods for media, directories, mkdir, move, or delete; those tools
  remain server-side.
```

- [ ] **Step 3: Update testing documentation**

In `docs/architecture/11-testing-and-observability.md`, add under backend testing:

```text
- ACP client-capability tests cover filesystem routing, outside-root fallback, terminal
  foreground/background/timeout/close behavior, and real stdio fs and terminal calls.
```

- [ ] **Step 4: Run the full checks**

Run:

```powershell
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-providers -q
uv run pytest packages/agentbox-api -q
uv run ruff check --fix packages
uv run ty check packages
cd apps/web
bun run test
bun run build
```

Expected: all PASS, except the known KI-1 rust-analyzer integration failure if it is still present. Record any failure explicitly.

- [ ] **Step 5: Run `git diff --check`**

Run: `git diff --check`

Expected: no output.

- [ ] **Step 6: Commit**

```powershell
git add docs/ROADMAP.md docs/architecture/07-protocols.md docs/architecture/11-testing-and-observability.md
git commit -m "docs: document ACP client capability support"
```

---

## Final Review Checklist

- [ ] Both ACP filesystem methods are implemented: `fs/read_text_file`, `fs/write_text_file`.
- [ ] All ACP terminal methods are implemented: create, output, wait_for_exit, kill, release.
- [ ] Capability negotiation honors absent/read-only/write-only/terminal combinations.
- [ ] Only bound tools are overridden.
- [ ] Paths outside project/extra roots fall back to server-side tools.
- [ ] Composed `append_file`, `edit_file`, and `copy_file` work through ACP read/write.
- [ ] Non-ACP tools remain server-side and are documented as such.
- [ ] ACP terminals are released on close and delete.
- [ ] Unit, adapter, and stdio tests cover the new paths.
- [ ] `docs/ROADMAP.md` and `docs/architecture` describe the implemented behavior.
- [ ] Ruff, Ty, backend tests, frontend tests, and frontend build pass (or KI-1 is the only known failure).
