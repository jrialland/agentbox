import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const fake = vi.hoisted(() => ({
  events: [] as Record<string, unknown>[],
  stream: vi.fn(),
}));

vi.mock("./agent", () => ({ streamChat: fake.stream }));

import { useChat } from "./useChat";

describe("useChat", () => {
  beforeEach(() => {
    fake.events = [];
    fake.stream.mockReset();
    fake.stream.mockImplementation(async function* () {
      for (const event of fake.events) yield event;
    });
  });

  it("keeps interleaved AG-UI segments in event order", async () => {
    fake.events = [
      { type: "TEXT_MESSAGE_START", messageId: "m1" },
      { type: "TEXT_MESSAGE_CONTENT", messageId: "m1", delta: "hello" },
      { type: "TOOL_CALL_START", toolCallId: "c1", toolCallName: "read" },
      { type: "TOOL_CALL_ARGS", toolCallId: "c1", delta: "{}" },
      { type: "TOOL_CALL_RESULT", toolCallId: "c1", content: "ok" },
      { type: "REASONING_MESSAGE_START", messageId: "r1" },
      { type: "REASONING_MESSAGE_CONTENT", messageId: "r1", delta: "hmm" },
      { type: "REASONING_MESSAGE_END", messageId: "r1" },
      { type: "TEXT_MESSAGE_CONTENT", messageId: "m1", delta: " world" },
      { type: "TEXT_MESSAGE_END", messageId: "m1" },
      { type: "RUN_FINISHED" },
    ];
    const { result } = renderHook(() => useChat("http://api", "token", "s1"));

    await act(async () => {
      await result.current.send("hi", { mode: "agent" });
    });

    expect(fake.stream).toHaveBeenCalledWith(
      expect.objectContaining({ content: "hi", sessionId: "s1" }),
    );
    expect(result.current.segments.map((segment) => segment.kind)).toEqual([
      "text",
      "tool",
      "reasoning",
    ]);
    expect(result.current.segments[0]).toMatchObject({
      kind: "text",
      text: "hello world",
      status: "done",
    });
    expect(result.current.segments[1]).toMatchObject({
      kind: "tool",
      name: "read",
      result: "ok",
      status: "success",
    });
    expect(result.current.segments[2]).toMatchObject({
      kind: "reasoning",
      text: "hmm",
      status: "done",
    });
    expect(result.current.running).toBe(false);
    expect(result.current.runStatus).toBe("idle");
  });

  it("accumulates anonymous text chunks into one segment", async () => {
    fake.events = [
      { type: "TEXT_MESSAGE_CHUNK", delta: "hel" },
      { type: "TEXT_MESSAGE_CHUNK", delta: "lo" },
      { type: "RUN_FINISHED" },
    ];
    const { result } = renderHook(() => useChat("http://api", "token", "s1"));

    await act(async () => {
      await result.current.send("hi", { mode: "agent" });
    });

    expect(result.current.segments).toHaveLength(1);
    expect(result.current.segments[0]).toMatchObject({
      kind: "text",
      text: "hello",
      status: "done",
    });
  });

  it("sets error and stops running on RUN_ERROR", async () => {
    fake.events = [
      { type: "TEXT_MESSAGE_START", messageId: "m1" },
      { type: "RUN_ERROR", message: "boom" },
    ];
    const { result } = renderHook(() => useChat("http://api", "token", "s1"));

    await act(async () => {
      await result.current.send("hi", { mode: "agent" });
    });

    expect(result.current.error).toBe("boom");
    expect(result.current.segments[0]).toMatchObject({ kind: "text", status: "done" });
    expect(result.current.running).toBe(false);
  });
});
