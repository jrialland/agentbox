from __future__ import annotations

import pathlib
import sys

from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from pydantic_ai.models.test import TestModel

from agentbox_api.plugin_hook_config import CommandAction, HookEvent, PluginHook
from agentbox_api.plugin_hooks import (
    PluginHookRef,
    PluginHookRuntime,
    PluginHooks,
)
from agentbox_harness.events import EventBus
from agentbox_harness.harness import Harness
from agentbox_harness.session import InMemoryMessageLogStore
from agentbox_harness.spec import (
    AgentSpec,
    Mode,
    ModelBinding,
    NativeToolBinding,
)
from agentbox_harness.tools.registry import ToolRegistry


def _has_tool_return(messages) -> bool:
    return any(
        getattr(part, "part_kind", "") == "tool-return"
        for message in messages
        for part in message.parts
    )


def _script(tmp_path: pathlib.Path, name: str, body: str) -> pathlib.Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _command_hook(hook_id: str, event: HookEvent, script: pathlib.Path) -> PluginHook:
    return PluginHook(
        id=hook_id,
        event=event,
        action=CommandAction(
            type="command",
            command=sys.executable,
            args=[str(script)],
            timeout_ms=5000,
        ),
    )


def _ref(tmp_path: pathlib.Path, hook: PluginHook) -> PluginHookRef:
    return PluginHookRef(
        plugin="acme",
        root=tmp_path,
        data=tmp_path / "data",
        hook=hook,
    )


def _spec() -> AgentSpec:
    return AgentSpec(
        name="coder",
        description="d",
        instructions="i",
        tool_bindings=[NativeToolBinding(name="write_file")],
        mode_definitions=[Mode(name="agent", flags={"write": True})],
        model_binding=ModelBinding(model="test", provider="test"),
    )


async def test_hooks_mutate_args_replace_result_and_inject_context(tmp_path):
    registry = ToolRegistry()
    seen: list[tuple[str, str]] = []

    async def write_file(path: str, content: str) -> str:
        seen.append((path, content))
        return "original"

    registry.register_native("write_file", write_file, required_flags=("write",))
    harness = Harness(
        registry=registry,
        model=TestModel(),
        store_factory=InMemoryMessageLogStore,
    )
    session = harness.start_session(
        _spec(), project_root=str(tmp_path), mode_name="agent"
    )

    before = _command_hook(
        "before",
        "before_tool",
        _script(
            tmp_path,
            "before.py",
            "import json,sys\n"
            "json.load(sys.stdin)\n"
            "print(json.dumps({"
            "'args': {'path': 'hooked.txt', 'content': 'x'}, "
            "'context': 'before-note'"
            "}))\n",
        ),
    )
    after = _command_hook(
        "after",
        "after_tool",
        _script(
            tmp_path,
            "after.py",
            "import json,sys\n"
            "json.load(sys.stdin)\n"
            "print(json.dumps({'result': 'replaced', 'context': 'after-note'}))\n",
        ),
    )
    session_start = _command_hook(
        "session",
        "session_start",
        _script(
            tmp_path,
            "session.py",
            "print('{\"context\": \"session-note\"}')\n",
        ),
    )
    end_marker = tmp_path / "ended"
    session_end = _command_hook(
        "end",
        "session_end",
        _script(
            tmp_path,
            "end.py",
            "import os,pathlib\n"
            f"pathlib.Path({str(end_marker)!r}).write_text('1', encoding='utf-8')\n",
        ),
    )
    runtime = PluginHookRuntime()
    harness.plugin_hooks = PluginHooks(
        runtime,
        session.session_id,
        "p1",
        str(tmp_path),
        (
            _ref(tmp_path, session_start),
            _ref(tmp_path, before),
            _ref(tmp_path, after),
            _ref(tmp_path, session_end),
        ),
    )

    captured = []

    async def stream_fn(messages, info):
        captured.append(messages)
        if not _has_tool_return(messages):
            yield {
                0: DeltaToolCall(
                    name="write_file",
                    json_args='{"path": "original.txt", "content": "x"}',
                    tool_call_id="call-1",
                )
            }
            return
        yield "done"

    outcome = await harness.run_turn(
        session,
        "write",
        bus=EventBus(),
        model_override=FunctionModel(stream_function=stream_fn),
    )
    assert outcome.status == "success", outcome
    assert seen == [("hooked.txt", "x")]

    system_text = "\n".join(
        str(getattr(part, "content", ""))
        for message in captured[0]
        for part in message.parts
    )
    assert "session-note" in system_text

    tool_text = "\n".join(
        str(getattr(part, "content", ""))
        for message in captured[-1]
        for part in message.parts
        if getattr(part, "part_kind", "") == "tool-return"
    )
    assert "replaced" in tool_text
    assert "before-note" in tool_text
    assert "after-note" in tool_text

    await runtime.end_session(session.session_id)
    assert end_marker.read_text(encoding="utf-8") == "1"


async def test_before_tool_hook_can_deny(tmp_path):
    registry = ToolRegistry()
    executed = False

    async def write_file(path: str, content: str) -> str:
        nonlocal executed
        executed = True
        return "ok"

    registry.register_native("write_file", write_file, required_flags=("write",))
    harness = Harness(
        registry=registry,
        model=TestModel(),
        store_factory=InMemoryMessageLogStore,
    )
    session = harness.start_session(
        _spec(), project_root=str(tmp_path), mode_name="agent"
    )
    deny = _command_hook(
        "deny",
        "before_tool",
        _script(
            tmp_path,
            "deny.py",
            "import json,sys\n"
            "json.load(sys.stdin)\n"
            "print(json.dumps({'decision': 'deny', 'reason': 'blocked'}))\n",
        ),
    )
    runtime = PluginHookRuntime()
    harness.plugin_hooks = PluginHooks(
        runtime, session.session_id, "p1", str(tmp_path), (_ref(tmp_path, deny),)
    )

    captured = []

    async def stream_fn(messages, info):
        captured.append(messages)
        if not _has_tool_return(messages):
            yield {
                0: DeltaToolCall(
                    name="write_file",
                    json_args='{"path": "a.txt", "content": "x"}',
                    tool_call_id="call-1",
                )
            }
            return
        yield "done"

    outcome = await harness.run_turn(
        session,
        "write",
        bus=EventBus(),
        model_override=FunctionModel(stream_function=stream_fn),
    )
    assert outcome.status == "success", outcome
    assert executed is False
    tool_text = "\n".join(
        str(getattr(part, "content", ""))
        for message in captured[-1]
        for part in message.parts
        if getattr(part, "part_kind", "") == "tool-return"
    )
    assert "blocked" in tool_text
