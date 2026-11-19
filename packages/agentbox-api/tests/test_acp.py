import base64

from acp import schema as s

from agentbox_api.acp_server import prompt_parts


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def test_prompt_parts_text_and_link():
    parts = prompt_parts([
        s.TextContentBlock(text="hello"),
        s.ResourceContentBlock(uri="file:///x.py", name="x.py", mime_type="text/x-python"),
    ])
    assert parts[0] == "hello"
    assert "x.py" in parts[1]


def test_prompt_parts_image_and_audio():
    parts = prompt_parts([
        s.ImageContentBlock(data=_b64(b"img"), mime_type="image/png"),
        s.AudioContentBlock(data=_b64(b"aud"), mime_type="audio/wav"),
    ])
    assert parts[0].media_type == "image/png"
    assert parts[1].media_type == "audio/wav"


def test_prompt_parts_embedded_text():
    parts = prompt_parts([
        s.EmbeddedResourceContentBlock(
            resource={"uri": "file:///a.txt", "text": "hi", "mimeType": "text/plain"}
        )
    ])
    assert "hi" in parts[0]


def test_text_delta_maps_to_agent_message_chunk():
    from pydantic_ai.messages import PartDeltaEvent, TextPartDelta

    from agentbox_api.acp_server import update_for_event

    upd = update_for_event(PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="hi")))
    assert upd.session_update == "agent_message_chunk"
    assert upd.content.text == "hi"


def test_tool_call_start_and_result():
    from pydantic_ai.messages import (
        FunctionToolCallEvent,
        FunctionToolResultEvent,
        ToolCallPart,
        ToolReturnPart,
    )

    from agentbox_api.acp_server import update_for_event

    call = FunctionToolCallEvent(
        part=ToolCallPart(tool_name="read_text_file", args={}, tool_call_id="c1")
    )
    start = update_for_event(call)
    assert start.session_update == "tool_call"
    assert start.tool_call_id == "c1"
    done = update_for_event(
        FunctionToolResultEvent(
            part=ToolReturnPart(tool_name="read_text_file", content="ok", tool_call_id="c1")
        )
    )
    assert done.session_update == "tool_call_update"
    assert done.status == "completed"
