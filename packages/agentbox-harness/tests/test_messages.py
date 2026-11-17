from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from agentbox_harness.messages import turns_to_messages
from agentbox_harness.session import Turn


def test_turns_to_messages_maps_roles():
    turns = [
        Turn(id="t1", role="user", content="hello", parent_id=None),
        Turn(id="t2", role="assistant", content="hi there", parent_id="t1"),
    ]
    msgs = turns_to_messages(turns)

    assert len(msgs) == 2
    assert isinstance(msgs[0], ModelRequest)
    assert isinstance(msgs[1], ModelResponse)
    assert isinstance(msgs[0].parts[0], UserPromptPart)
    assert msgs[0].parts[0].content == "hello"
    assert isinstance(msgs[1].parts[0], TextPart)
    assert msgs[1].parts[0].content == "hi there"


def test_turns_to_messages_skips_unknown_roles():
    turns = [
        Turn(id="t1", role="user", content="hello", parent_id=None),
        Turn(id="t2", role="tool", content="ignored", parent_id="t1"),
    ]
    msgs = turns_to_messages(turns)
    assert len(msgs) == 1
