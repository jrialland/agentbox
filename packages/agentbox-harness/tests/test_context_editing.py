from types import SimpleNamespace

from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.messages import (
    BinaryContent,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestContext, ModelRequestParameters
from pydantic_ai.models.test import TestModel

from agentbox_harness.context_editing import (
    ContextEditingConfig,
    ContextEditingStats,
    apply_context_edits,
    estimate_messages_tokens,
    make_context_editing_processor,
)
from agentbox_harness.events import EventBus
from agentbox_harness.harness import Harness
from agentbox_harness.session import InMemoryMessageLogStore
from agentbox_harness.spec import DEFAULT_MODES, AgentSpec, ModelBinding
from agentbox_harness.tools.registry import ToolRegistry

LONG = "x" * 4000


def _pair(call_id: str, name: str, result: str = LONG, args=None):
    return [
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=name,
                    args=args or {"q": "x"},
                    tool_call_id=call_id,
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name=name, content=result, tool_call_id=call_id
                )
            ]
        ),
    ]


def _pairs(count: int):
    messages = []
    for index in range(count):
        messages.extend(_pair(str(index), "read_file", f"{LONG}-{index}"))
    return messages


def _result(message) -> str:
    part = message.parts[0]
    assert isinstance(part, ToolReturnPart)
    content = part.content
    assert isinstance(content, str)
    return content


def _call(message) -> ToolCallPart:
    part = message.parts[0]
    assert isinstance(part, ToolCallPart)
    return part


def _prompt_items(message) -> list:
    part = message.parts[0]
    assert isinstance(part, UserPromptPart)
    content = part.content
    assert isinstance(content, list)
    return content


def test_no_trigger_below_threshold():
    messages = _pair("1", "read_file", "small")
    config = ContextEditingConfig(trigger_tokens=10_000)
    edited, stats = apply_context_edits(
        messages, trigger_tokens=10_000, config=config
    )
    assert edited == messages
    assert stats.triggered is False


def test_clears_oldest_and_keeps_last_three():
    messages = _pairs(6)
    config = ContextEditingConfig(
        trigger_tokens=2_000,
        target_ratio=0.6,
        keep_tool_results=3,
        keep_recent_messages=2,
    )
    edited, stats = apply_context_edits(
        messages, trigger_tokens=2_000, config=config
    )
    assert stats.triggered is True
    assert stats.cleared_tool_results == 2
    assert _result(edited[1]) == config.placeholder
    assert _result(edited[3]) == config.placeholder
    assert _result(edited[5]).startswith(LONG)
    assert _result(edited[7]).startswith(LONG)
    assert _result(edited[9]).startswith(LONG)
    assert _result(edited[11]).startswith(LONG)
    assert stats.after_tokens < stats.before_tokens


def test_keep_recent_messages_protects_tool_return():
    messages = _pairs(6)
    config = ContextEditingConfig(
        trigger_tokens=2_000,
        keep_tool_results=0,
        keep_recent_messages=6,
    )
    edited, stats = apply_context_edits(
        messages, trigger_tokens=2_000, config=config
    )
    assert stats.cleared_tool_results == 3
    assert _result(edited[1]) == config.placeholder
    assert _result(edited[3]) == config.placeholder
    assert _result(edited[5]) == config.placeholder
    assert _result(edited[7]).startswith(LONG)
    assert _result(edited[9]).startswith(LONG)
    assert _result(edited[11]).startswith(LONG)


def test_exclude_tools():
    messages = _pair("1", "todo_list") + _pair("2", "read_file")
    config = ContextEditingConfig(
        trigger_tokens=100,
        target_ratio=0.1,
        keep_tool_results=0,
        keep_recent_messages=0,
        exclude_tools=("todo_list",),
    )
    edited, stats = apply_context_edits(
        messages, trigger_tokens=100, config=config
    )
    assert stats.cleared_tool_results == 1
    assert _result(edited[1]).startswith(LONG)
    assert _result(edited[3]) == config.placeholder


def test_already_cleared_is_skipped():
    part = ToolReturnPart(
        tool_name="read_file",
        content=LONG,
        tool_call_id="1",
        metadata={"context_editing": {"cleared": True}},
    )
    messages = [
        ModelResponse(
            parts=[ToolCallPart(tool_name="read_file", args={}, tool_call_id="1")]
        ),
        ModelRequest(parts=[part]),
    ]
    config = ContextEditingConfig(
        trigger_tokens=100,
        keep_tool_results=0,
        keep_recent_messages=0,
    )
    edited, stats = apply_context_edits(
        messages, trigger_tokens=100, config=config
    )
    assert stats.triggered is True
    assert stats.cleared_tool_results == 0
    assert _result(edited[1]) == LONG


def test_clear_tool_inputs_preserves_provider_fields():
    messages = [
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="write_file",
                    args={"content": LONG},
                    tool_call_id="1",
                    id="call-1",
                    provider_name="openai",
                    provider_details={"a": 1},
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="write_file", content=LONG, tool_call_id="1"
                )
            ]
        ),
    ]
    config = ContextEditingConfig(
        trigger_tokens=100,
        target_ratio=0.1,
        keep_tool_results=0,
        keep_recent_messages=0,
        clear_tool_inputs=True,
    )
    edited, stats = apply_context_edits(
        messages, trigger_tokens=100, config=config
    )
    call = _call(edited[0])
    assert stats.cleared_tool_inputs == 1
    assert call.args == {}
    assert call.id == "call-1"
    assert call.provider_name == "openai"
    assert call.provider_details == {"a": 1}


def test_clears_old_binary_but_keeps_recent():
    old = ModelRequest(
        parts=[
            UserPromptPart(
                content=[
                    "look",
                    BinaryContent(data=b"x" * 5000, media_type="image/png"),
                ]
            )
        ]
    )
    recent = ModelRequest(
        parts=[
            UserPromptPart(
                content=[
                    "recent",
                    BinaryContent(data=b"y" * 5000, media_type="image/png"),
                ]
            )
        ]
    )
    config = ContextEditingConfig(
        trigger_tokens=100,
        target_ratio=0.1,
        keep_recent_messages=1,
        clear_binary=True,
    )
    edited, stats = apply_context_edits(
        [old, recent], trigger_tokens=100, config=config
    )
    assert stats.cleared_binary_items == 1
    assert _prompt_items(edited[0])[1] == config.binary_placeholder
    assert isinstance(_prompt_items(edited[1])[1], BinaryContent)


def test_estimate_counts_binary():
    text_only = ModelRequest(parts=[UserPromptPart("x" * 4000)])
    with_binary = ModelRequest(
        parts=[
            UserPromptPart(
                content=[
                    "x" * 4000,
                    BinaryContent(data=b"y" * 100_000, media_type="image/png"),
                ]
            )
        ]
    )
    assert estimate_messages_tokens([with_binary]) > estimate_messages_tokens(
        [text_only]
    )


def test_target_ratio_stops_clearing():
    messages = _pairs(6)
    config = ContextEditingConfig(
        trigger_tokens=2_000,
        target_ratio=0.9,
        keep_tool_results=0,
        keep_recent_messages=0,
    )
    edited, stats = apply_context_edits(
        messages, trigger_tokens=2_000, config=config
    )
    target = int(2_000 * 0.9)
    assert stats.cleared_tool_results < 6
    assert stats.after_tokens <= target or stats.cleared_tool_results == 6


def test_processor_uses_context_window(monkeypatch):
    captured = {}

    def fake_apply(messages, *, trigger_tokens, config):
        captured["trigger"] = trigger_tokens
        return messages, ContextEditingStats(
            triggered=True,
            before_tokens=1,
            after_tokens=1,
            trigger_tokens=trigger_tokens,
        )

    monkeypatch.setattr(
        "agentbox_harness.context_editing.apply_context_edits", fake_apply
    )
    ctx = SimpleNamespace(
        model=SimpleNamespace(profile={"context_window": 10_000})
    )
    process = make_context_editing_processor(
        ContextEditingConfig(trigger_tokens=100_000, trigger_ratio=0.8)
    )
    process(ctx, [])
    assert captured["trigger"] == 8_000


async def test_harness_forwards_context_editing(monkeypatch, tmp_path):
    from agentbox_harness.agent_factory import build_agent as real_build_agent

    captured = {}

    def fake_build_agent(*args, **kwargs):
        captured["context_editing"] = kwargs.get("context_editing")
        kwargs.pop("context_editing", None)
        return real_build_agent(*args, **kwargs)

    monkeypatch.setattr(
        "agentbox_harness.harness.build_agent", fake_build_agent
    )
    config = ContextEditingConfig()
    harness = Harness(
        registry=ToolRegistry(),
        model=TestModel(),
        store_factory=InMemoryMessageLogStore,
        context_editing=config,
    )
    spec = AgentSpec(
        name="coder",
        description="d",
        instructions="i",
        tool_bindings=[],
        mode_definitions=list(DEFAULT_MODES),
        model_binding=ModelBinding(model="test", provider="test"),
    )
    session = harness.start_session(
        spec, project_root=str(tmp_path), mode_name="agent"
    )
    outcome = await harness.run_turn(session, "hi", EventBus())
    assert outcome.status == "success"
    assert captured["context_editing"] is config


async def test_process_history_capability_runs_processor():
    config = ContextEditingConfig(
        trigger_tokens=1,
        keep_tool_results=0,
        keep_recent_messages=0,
    )
    ctx = SimpleNamespace(
        model=SimpleNamespace(profile={"context_window": 10_000}),
        messages=[],
    )
    messages = _pair("1", "read_file")
    request_context = ModelRequestContext(
        model=ctx.model,
        messages=messages,
        model_settings=None,
        model_request_parameters=ModelRequestParameters(),
    )
    capability = ProcessHistory(make_context_editing_processor(config))
    result = await capability.before_model_request(
        ctx,  # ty: ignore[invalid-argument-type]
        request_context,
    )
    assert _result(result.messages[1]) == config.placeholder


def test_processor_fails_open(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "agentbox_harness.context_editing.apply_context_edits", boom
    )
    ctx = SimpleNamespace(model=SimpleNamespace(profile={}))
    messages = _pair("1", "read_file", "small")
    process = make_context_editing_processor(ContextEditingConfig())
    assert process(ctx, messages) == messages
