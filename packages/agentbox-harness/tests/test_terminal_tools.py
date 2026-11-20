import asyncio
import os
import re
import sys

import pytest

from agentbox_harness.tools.terminal import JobManager, make_terminal_tools


def _py(code: str) -> str:
    if os.name == "nt":
        return f'& "{sys.executable}" -c "{code}"'
    return f'"{sys.executable}" -c "{code}"'


@pytest.fixture
async def manager():
    m = JobManager()
    try:
        yield m
    finally:
        await m.shutdown()


async def test_run_command_success(tmp_path, manager):
    tools = make_terminal_tools(manager, "s1", str(tmp_path), [tmp_path])
    out = await tools["run_command"]("echo hello")
    assert "hello" in out
    assert "exit code 0" in out


async def test_run_command_exit_code(tmp_path, manager):
    tools = make_terminal_tools(manager, "s1", str(tmp_path), [tmp_path])
    out = await tools["run_command"](_py("import sys; sys.exit(3)"))
    assert "exit code 3" in out


async def test_run_command_timeout(tmp_path, manager):
    tools = make_terminal_tools(manager, "s1", str(tmp_path), [tmp_path])
    out = await tools["run_command"](_py("import time; time.sleep(5)"), timeout=1)
    assert "timed out after 1s" in out


async def test_background_job_lifecycle(tmp_path, manager):
    tools = make_terminal_tools(manager, "s1", str(tmp_path), [tmp_path])
    started = await tools["run_command"](
        _py("import time; time.sleep(30)"), background=True
    )
    match = re.search(r"Started job (\w+)", started)
    assert match
    job_id = match.group(1)
    assert job_id in await tools["list_jobs"]()
    assert await tools["kill_job"](job_id) == f"Killed job {job_id}."
    await asyncio.sleep(0.2)
    assert "killed" in await tools["list_jobs"]()


async def test_background_output_tail(tmp_path, manager):
    tools = make_terminal_tools(manager, "s1", str(tmp_path), [tmp_path])
    started = await tools["run_command"](
        _py("print('ready', flush=True); import time; time.sleep(30)"),
        background=True,
    )
    match = re.search(r"Started job (\w+)", started)
    assert match
    job_id = match.group(1)
    output = ""
    for _ in range(50):
        output = await tools["get_job_output"](job_id)
        if "ready" in output:
            break
        await asyncio.sleep(0.1)
    assert "ready" in output
    await tools["kill_job"](job_id)


async def test_cwd_is_confined_to_allowed_roots(tmp_path, manager):
    root = tmp_path / "project"
    external = tmp_path / "external"
    outside = tmp_path / "outside"
    for path in (root, external, outside):
        path.mkdir()
    tools = make_terminal_tools(manager, "s1", str(root), [root, external])
    assert "ok" in await tools["run_command"]("echo ok", cwd=str(external))
    denied = await tools["run_command"]("echo no", cwd=str(outside))
    assert "cwd escapes allowed roots" in denied


async def test_job_limit(tmp_path):
    manager = JobManager(max_jobs=1)
    tools = make_terminal_tools(manager, "s1", str(tmp_path), [tmp_path])
    try:
        started = await tools["run_command"](
            _py("import time; time.sleep(30)"), background=True
        )
        match = re.search(r"Started job (\w+)", started)
        assert match
        job_id = match.group(1)
        denied = await tools["run_command"](
            _py("import time; time.sleep(30)"), background=True
        )
        assert "Job limit reached" in denied
        await tools["kill_job"](job_id)
    finally:
        await manager.shutdown()


async def test_kill_session_clears_jobs(tmp_path, manager):
    tools = make_terminal_tools(manager, "s1", str(tmp_path), [tmp_path])
    started = await tools["run_command"](
        _py("import time; time.sleep(30)"), background=True
    )
    match = re.search(r"Started job (\w+)", started)
    assert match
    job_id = match.group(1)
    await manager.kill_session("s1")
    assert manager.jobs("s1") == []
    assert manager.get("s1", job_id) is None
