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
