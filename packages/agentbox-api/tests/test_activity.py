from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartEndEvent,
    PartStartEvent,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)

from agentbox_api.activity import RunActivityCollector


def test_activity_collector_records_tools_and_reasoning():
    collector = RunActivityCollector()
    collector.observe(
        PartStartEvent(index=0, part=ThinkingPart(content="hmm"))
    )
    collector.observe(PartEndEvent(index=0, part=ThinkingPart(content="hmm")))
    collector.observe(
        FunctionToolCallEvent(
            part=ToolCallPart(
                tool_name="read_text_file", args={}, tool_call_id="c1"
            )
        )
    )
    collector.observe(
        FunctionToolResultEvent(
            part=ToolReturnPart(
                tool_name="read_text_file",
                content="ok",
                tool_call_id="c1",
                outcome="success",
            )
        )
    )
    summary = collector.summary("success")
    assert summary["status"] == "success"
    assert summary["reasoning_ms"] >= 0
    assert summary["reasoning_text"] == "hmm"
    assert summary["tools"] == [
        {
            "name": "read_text_file",
            "status": "success",
            "duration_ms": summary["tools"][0]["duration_ms"],
            "args": "{}",
            "result": "ok",
        }
    ]


def test_activity_collector_marks_failed_tool():
    collector = RunActivityCollector()
    collector.observe(
        FunctionToolCallEvent(
            part=ToolCallPart(tool_name="terminal", args={}, tool_call_id="c1")
        )
    )
    collector.observe(
        FunctionToolResultEvent(
            part=ToolReturnPart(
                tool_name="terminal",
                content="boom",
                tool_call_id="c1",
                outcome="failed",
            )
        )
    )
    assert collector.summary("error")["tools"][0]["status"] == "error"
