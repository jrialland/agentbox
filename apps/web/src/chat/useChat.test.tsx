import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const fake = vi.hoisted(() => ({
  handlers: {} as Record<string, (payload: unknown) => void>,
  added: [] as unknown[],
  run: vi.fn(async () => {
    const emit = (event: unknown) => fake.handlers.onEvent?.({ event });
    emit({ type: "TEXT_MESSAGE_START", messageId: "m1" });
    emit({ type: "TEXT_MESSAGE_CONTENT", messageId: "m1", delta: "hello" });
    emit({ type: "TOOL_CALL_START", toolCallId: "c1", toolCallName: "read" });
    emit({ type: "TOOL_CALL_ARGS", toolCallId: "c1", delta: "{}" });
    emit({ type: "TOOL_CALL_RESULT", toolCallId: "c1", content: "ok" });
    emit({ type: "REASONING_MESSAGE_START", messageId: "r1" });
    emit({ type: "REASONING_MESSAGE_CONTENT", messageId: "r1", delta: "hmm" });
    emit({ type: "REASONING_MESSAGE_END", messageId: "r1" });
    emit({ type: "TEXT_MESSAGE_CONTENT", messageId: "m1", delta: " world" });
    emit({ type: "TEXT_MESSAGE_END", messageId: "m1" });
    emit({ type: "RUN_FINISHED" });
  }),
}));

vi.mock("./agent", () => ({
  createChatAgent: vi.fn(() => ({
    subscribe: (handlers: Record<string, (payload: unknown) => void>) => {
      fake.handlers = handlers;
    },
    addMessage: (message: unknown) => fake.added.push(message),
    runAgent: fake.run,
  })),
}));

import { useChat } from "./useChat";

describe("useChat", () => {
  beforeEach(() => {
    fake.handlers = {};
    fake.added = [];
    fake.run.mockClear();
  });

  it("keeps interleaved AG-UI segments in event order", async () => {
    const { result } = renderHook(() => useChat("http://api", "token", "s1"));

    await act(async () => {
      await result.current.send("hi", { mode: "agent" });
    });

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

  it("sets error and stops running on RUN_ERROR", async () => {
    fake.run.mockImplementationOnce(async () => {
      fake.handlers.onEvent?.({ event: { type: "TEXT_MESSAGE_START", messageId: "m1" } });
      fake.handlers.onEvent?.({ event: { type: "RUN_ERROR", message: "boom" } });
    });
    const { result } = renderHook(() => useChat("http://api", "token", "s1"));

    await act(async () => {
      await result.current.send("hi", { mode: "agent" });
    });

    expect(result.current.error).toBe("boom");
    expect(result.current.segments[0]).toMatchObject({ kind: "text", status: "done" });
    expect(result.current.running).toBe(false);
  });
});
