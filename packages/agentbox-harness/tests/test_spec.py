from agentbox_harness.spec import (
    DEFAULT_MODES,
    AgentSpec,
    Mode,
    ModelBinding,
    NativeToolBinding,
)


def test_mode_allows():
    ask = Mode(name="ask", flags={"write": False})
    agent = Mode(name="agent", flags={"write": True})
    assert not ask.allows("write")
    assert agent.allows("write")
    assert ask.allows("read")  # unknown flags default to True


def test_agent_spec_round_trips_json():
    spec = AgentSpec(
        name="coder",
        description="Writes code",
        instructions="You are a helpful coding assistant.",
        tool_bindings=[NativeToolBinding(name="read_text_file")],
        mode_definitions=list(DEFAULT_MODES),
        model_binding=ModelBinding(model="gpt-x", provider="openai"),
    )
    restored = AgentSpec.model_validate_json(spec.model_dump_json())
    assert restored == spec


def test_default_modes():
    by_name = {m.name: m for m in DEFAULT_MODES}
    assert set(by_name) == {"ask", "agent"}
    assert by_name["ask"].allows("write") is False
    assert by_name["agent"].allows("write") is True
