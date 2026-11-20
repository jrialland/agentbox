import { describe, expect, it } from "vitest";

import { applyAgUiEvent, emptySegments, finalizeSegments } from "./segments";

describe("segment order", () => {
  it("keeps reasoning, tool, reasoning, text order", () => {
    let state = emptySegments();
    state = applyAgUiEvent(state, {
      type: "REASONING_MESSAGE_START",
      messageId: "r1",
    });
    state = applyAgUiEvent(state, {
      type: "REASONING_MESSAGE_CONTENT",
      messageId: "r1",
      delta: "hmm",
    });
    state = applyAgUiEvent(state, {
      type: "REASONING_MESSAGE_END",
      messageId: "r1",
    });
    state = applyAgUiEvent(state, {
      type: "TOOL_CALL_START",
      toolCallId: "c1",
      toolCallName: "list_directory",
    });
    state = applyAgUiEvent(state, {
      type: "TOOL_CALL_RESULT",
      toolCallId: "c1",
      content: "ok",
    });
    state = applyAgUiEvent(state, {
      type: "REASONING_MESSAGE_START",
      messageId: "r2",
    });
    state = applyAgUiEvent(state, {
      type: "REASONING_MESSAGE_CONTENT",
      messageId: "r2",
      delta: "again",
    });
    state = applyAgUiEvent(state, {
      type: "REASONING_MESSAGE_END",
      messageId: "r2",
    });
    state = applyAgUiEvent(state, {
      type: "TEXT_MESSAGE_START",
      messageId: "t1",
    });
    state = applyAgUiEvent(state, {
      type: "TEXT_MESSAGE_CONTENT",
      messageId: "t1",
      delta: "answer",
    });
    state = applyAgUiEvent(state, {
      type: "TEXT_MESSAGE_END",
      messageId: "t1",
    });

    expect(state.map((segment) => segment.kind)).toEqual([
      "reasoning",
      "tool",
      "reasoning",
      "text",
    ]);
    expect(state[3]).toMatchObject({ kind: "text", text: "answer" });
  });

  it("ignores unknown ids and finalizes cancelled tool calls", () => {
    let state = applyAgUiEvent(emptySegments(), {
      type: "TOOL_CALL_START",
      toolCallId: "c1",
      toolCallName: "terminal",
    });
    state = applyAgUiEvent(state, {
      type: "TOOL_CALL_ARGS",
      toolCallId: "missing",
      delta: "{}",
    });
    state = finalizeSegments(state, "cancelled");
    expect(state[0]).toMatchObject({
      kind: "tool",
      status: "cancelled",
    });
  });
});
