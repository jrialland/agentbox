from __future__ import annotations

import pathlib
from typing import Any, Literal, cast

import pytest
from pydantic_ai.exceptions import ToolFailed
from pydantic_ai.messages import ToolCallPart, ToolReturn
from pydantic_ai.tools import RunContext, ToolDefinition

from agentbox_api.plugin_hook_config import ContextAction, HookEvent, PluginHook
from agentbox_api.plugin_hooks import (
    HookContext,
    HookExecutor,
    HookResult,
    PluginHookRef,
    PluginHookRuntime,
    PluginHooks,
)


class FakeExecutor:
    def __init__(self, results: dict[str, HookResult | Exception]):
        self.results = results
        self.calls: list[tuple[str, str]] = []

    async def execute(self, hook, context: HookContext) -> HookResult:
        self.calls.append((hook.id, context.event))
        result = self.results.get(hook.id, HookResult())
        if isinstance(result, Exception):
            raise result
        return result


class FakeCtx:
    run_id = "run-1"

    def __init__(self):
        self.enqueued = []

    def enqueue(self, *content, **kwargs):
        self.enqueued.extend(content)


def _executor(results: dict[str, HookResult | Exception]) -> FakeExecutor:
    return FakeExecutor(results)


def _runtime(executor: FakeExecutor) -> PluginHookRuntime:
    return PluginHookRuntime(cast(HookExecutor, executor))


def _ctx() -> RunContext[Any]:
    return cast(RunContext[Any], FakeCtx())


def _ref(
    tmp_path: pathlib.Path,
    hook_id: str = "h",
    event: HookEvent = "before_tool",
    tools: tuple[str, ...] = (),
    on_error: Literal["ignore", "deny"] = "ignore",
    text: str = "x",
) -> PluginHookRef:
    hook = PluginHook(
        id=hook_id,
        event=event,
        tools=list(tools),
        on_error=on_error,
        action=ContextAction(type="context", text=text),
    )
    return PluginHookRef(
        plugin="acme",
        root=tmp_path / "plugin",
        data=tmp_path / "data",
        hook=hook,
    )


def _capability(
    runtime: PluginHookRuntime, refs: list[PluginHookRef], tmp_path: pathlib.Path
) -> PluginHooks:
    return PluginHooks(runtime, "s1", "p1", str(tmp_path), tuple(refs))


def _call() -> ToolCallPart:
    return ToolCallPart(
        tool_name="write_file",
        args={"path": "a"},
        tool_call_id="c1",
    )


def _tool_def() -> ToolDefinition:
    return ToolDefinition(name="write_file")


async def test_before_tool_denies(tmp_path):
    executor = FakeExecutor({"h": HookResult(decision="deny", reason="no secrets")})
    runtime = _runtime(executor)
    hooks = _capability(runtime, [_ref(tmp_path)], tmp_path)
    with pytest.raises(ToolFailed, match="no secrets"):
        await hooks.before_tool_execute(
            _ctx(), call=_call(), tool_def=_tool_def(), args={"path": "a"}
        )


async def test_before_tool_replaces_args(tmp_path):
    executor = FakeExecutor({"h": HookResult(args={"path": "b"})})
    runtime = _runtime(executor)
    hooks = _capability(runtime, [_ref(tmp_path)], tmp_path)
    args = await hooks.before_tool_execute(
        _ctx(), call=_call(), tool_def=_tool_def(), args={"path": "a"}
    )
    assert args == {"path": "b"}


async def test_before_and_after_context_appended(tmp_path):
    executor = FakeExecutor(
        {
            "before": HookResult(context="before"),
            "after": HookResult(context="after"),
        }
    )
    runtime = _runtime(executor)
    refs = [
        _ref(tmp_path, "before", "before_tool"),
        _ref(tmp_path, "after", "after_tool"),
    ]
    hooks = _capability(runtime, refs, tmp_path)
    ctx = _ctx()
    await hooks.before_tool_execute(
        ctx, call=_call(), tool_def=_tool_def(), args={"path": "a"}
    )
    result = await hooks.after_tool_execute(
        ctx,
        call=_call(),
        tool_def=_tool_def(),
        args={"path": "a"},
        result="R",
    )
    assert result == "R\n\nbefore\n\nafter"


async def test_after_tool_replaces_result(tmp_path):
    executor = FakeExecutor({"h": HookResult(result="new", context="note")})
    runtime = _runtime(executor)
    hooks = _capability(runtime, [_ref(tmp_path, "h", "after_tool")], tmp_path)
    result = await hooks.after_tool_execute(
        _ctx(),
        call=_call(),
        tool_def=_tool_def(),
        args={},
        result="old",
    )
    assert result == "new\n\nnote"


async def test_tool_error_recovers(tmp_path):
    executor = FakeExecutor({"h": HookResult(result="recovered", context="note")})
    runtime = _runtime(executor)
    hooks = _capability(runtime, [_ref(tmp_path, "h", "tool_error")], tmp_path)
    result = await hooks.on_tool_execute_error(
        _ctx(),
        call=_call(),
        tool_def=_tool_def(),
        args={},
        error=RuntimeError("boom"),
    )
    assert result == "recovered\n\nnote"


async def test_tool_error_context_without_result_fails(tmp_path):
    executor = FakeExecutor({"h": HookResult(context="retry later")})
    runtime = _runtime(executor)
    hooks = _capability(runtime, [_ref(tmp_path, "h", "tool_error")], tmp_path)
    with pytest.raises(ToolFailed, match="retry later"):
        await hooks.on_tool_execute_error(
            _ctx(),
            call=_call(),
            tool_def=_tool_def(),
            args={},
            error=RuntimeError("boom"),
        )


async def test_run_start_context_enqueued_and_session_start_once(tmp_path):
    executor = FakeExecutor(
        {
            "session": HookResult(context="session-note"),
            "run": HookResult(context="run-note"),
        }
    )
    runtime = _runtime(executor)
    refs = [
        _ref(tmp_path, "session", "session_start"),
        _ref(tmp_path, "run", "run_start"),
    ]
    hooks = _capability(runtime, refs, tmp_path)
    raw = FakeCtx()
    ctx = cast(RunContext[Any], raw)
    await hooks.before_run(ctx)
    assert len(raw.enqueued) == 1
    part = raw.enqueued[0]
    assert part.content == "session-note\n\nrun-note"
    assert part.scope == "request"

    await hooks.before_run(ctx)
    assert len(raw.enqueued) == 2
    assert raw.enqueued[1].content == "run-note"
    assert [call for call in executor.calls if call[1] == "session_start"] == [
        ("session", "session_start")
    ]


async def test_session_end_runs_hooks(tmp_path):
    executor = FakeExecutor({"end": HookResult()})
    runtime = _runtime(executor)
    hooks = _capability(runtime, [_ref(tmp_path, "end", "session_end")], tmp_path)
    await hooks.before_run(_ctx())
    await runtime.end_session("s1")
    assert ("end", "session_end") in executor.calls


async def test_matcher_skips_other_tools(tmp_path):
    executor = FakeExecutor({"h": HookResult(context="x")})
    runtime = _runtime(executor)
    hooks = _capability(
        runtime, [_ref(tmp_path, "h", "before_tool", tools=("other",))], tmp_path
    )
    args = await hooks.before_tool_execute(
        _ctx(), call=_call(), tool_def=_tool_def(), args={"path": "a"}
    )
    assert args == {"path": "a"}
    assert executor.calls == []


async def test_on_error_deny_vs_ignore(tmp_path):
    executor = FakeExecutor({"h": RuntimeError("broken")})
    runtime = _runtime(executor)
    hooks = _capability(
        runtime, [_ref(tmp_path, "h", "before_tool", on_error="deny")], tmp_path
    )
    with pytest.raises(ToolFailed, match="broken"):
        await hooks.before_tool_execute(
            _ctx(), call=_call(), tool_def=_tool_def(), args={"path": "a"}
        )

    runtime = _runtime(FakeExecutor({"h": RuntimeError("broken")}))
    hooks = _capability(runtime, [_ref(tmp_path, "h", "before_tool")], tmp_path)
    args = await hooks.before_tool_execute(
        _ctx(), call=_call(), tool_def=_tool_def(), args={"path": "a"}
    )
    assert args == {"path": "a"}


async def test_tool_return_context_preserves_content(tmp_path):
    executor = FakeExecutor({"h": HookResult(context="note")})
    runtime = _runtime(executor)
    hooks = _capability(runtime, [_ref(tmp_path, "h", "after_tool")], tmp_path)
    result = await hooks.after_tool_execute(
        _ctx(),
        call=_call(),
        tool_def=_tool_def(),
        args={},
        result=ToolReturn(return_value={"ok": True}, content="extra"),
    )
    assert isinstance(result, ToolReturn)
    assert result.return_value == {"ok": True}
    assert result.content == "extra\n\nnote"


async def test_run_error_is_reraised_and_logged(tmp_path):
    executor = FakeExecutor({"err": HookResult()})
    runtime = _runtime(executor)
    hooks = _capability(runtime, [_ref(tmp_path, "err", "run_error")], tmp_path)
    with pytest.raises(RuntimeError, match="boom"):
        await hooks.on_run_error(_ctx(), error=RuntimeError("boom"))
    assert ("err", "run_error") in executor.calls
