import type { AppTab } from "./apps";

export type Segment =
  | {
      id: string;
      kind: "reasoning";
      text: string;
      status: "streaming" | "done";
      startedAt: number;
      endedAt?: number;
    }
  | {
      id: string;
      kind: "tool";
      toolCallId: string;
      name: string;
      args: string;
      result?: string;
      status: "running" | "success" | "error" | "cancelled";
      startedAt: number;
      endedAt?: number;
    }
  | {
      id: string;
      kind: "text";
      messageId: string;
      text: string;
      status: "streaming" | "done";
    }
  | {
      id: string;
      kind: "app";
      messageId: string;
      tab: AppTab;
    };

export type AgUiEvent =
  | { type: "TEXT_MESSAGE_START"; messageId: string }
  | { type: "TEXT_MESSAGE_CONTENT"; messageId: string; delta: string }
  | { type: "TEXT_MESSAGE_END"; messageId: string }
  | { type: "REASONING_MESSAGE_START"; messageId: string }
  | { type: "REASONING_MESSAGE_CONTENT"; messageId: string; delta: string }
  | { type: "REASONING_MESSAGE_END"; messageId: string }
  | { type: "TOOL_CALL_START"; toolCallId: string; toolCallName: string }
  | { type: "TOOL_CALL_ARGS"; toolCallId: string; delta: string }
  | { type: "TOOL_CALL_END"; toolCallId: string }
  | { type: "TOOL_CALL_RESULT"; toolCallId: string; content: unknown }
  | { type: "ACTIVITY_SNAPSHOT"; messageId: string; tab: AppTab };

export function emptySegments(): Segment[] {
  return [];
}

function updateById(
  segments: Segment[],
  id: string,
  update: (segment: Segment) => Segment,
): Segment[] {
  return segments.map((segment) => (segment.id === id ? update(segment) : segment));
}

export function applyAgUiEvent(
  segments: Segment[],
  event: AgUiEvent,
): Segment[] {
  switch (event.type) {
    case "TEXT_MESSAGE_START":
      return [
        ...segments,
        {
          id: event.messageId,
          kind: "text",
          messageId: event.messageId,
          text: "",
          status: "streaming",
        },
      ];
    case "TEXT_MESSAGE_CONTENT":
      return updateById(segments, event.messageId, (segment) =>
        segment.kind === "text"
          ? { ...segment, text: segment.text + event.delta }
          : segment,
      );
    case "TEXT_MESSAGE_END":
      return segments.flatMap((segment) => {
        if (segment.id !== event.messageId) return [segment];
        if (segment.kind !== "text") return [segment];
        return segment.text ? [{ ...segment, status: "done" }] : [];
      });
    case "REASONING_MESSAGE_START":
      return [
        ...segments,
        {
          id: event.messageId,
          kind: "reasoning",
          text: "",
          status: "streaming",
          startedAt: Date.now(),
        },
      ];
    case "REASONING_MESSAGE_CONTENT":
      return updateById(segments, event.messageId, (segment) =>
        segment.kind === "reasoning"
          ? { ...segment, text: segment.text + event.delta }
          : segment,
      );
    case "REASONING_MESSAGE_END":
      return segments.flatMap((segment) => {
        if (segment.id !== event.messageId) return [segment];
        if (segment.kind !== "reasoning") return [segment];
        return segment.text
          ? [{ ...segment, status: "done", endedAt: Date.now() }]
          : [];
      });
    case "TOOL_CALL_START":
      return [
        ...segments,
        {
          id: event.toolCallId,
          kind: "tool",
          toolCallId: event.toolCallId,
          name: event.toolCallName,
          args: "",
          status: "running",
          startedAt: Date.now(),
        },
      ];
    case "TOOL_CALL_ARGS":
      return updateById(segments, event.toolCallId, (segment) =>
        segment.kind === "tool"
          ? { ...segment, args: segment.args + event.delta }
          : segment,
      );
    case "TOOL_CALL_END":
      return segments;
    case "TOOL_CALL_RESULT":
      return updateById(segments, event.toolCallId, (segment) =>
        segment.kind === "tool"
          ? {
              ...segment,
              result: stringifyResult(event.content),
              status: "success",
              endedAt: Date.now(),
            }
          : segment,
      );
    case "ACTIVITY_SNAPSHOT":
      return [
        ...segments,
        {
          id: event.messageId,
          kind: "app",
          messageId: event.messageId,
          tab: event.tab,
        },
      ];
    default:
      return segments;
  }
}

export function finalizeSegments(
  segments: Segment[],
  status: "success" | "cancelled" | "error",
): Segment[] {
  const now = Date.now();
  return segments.map((segment) => {
    if (segment.kind === "reasoning" && segment.status === "streaming") {
      return { ...segment, status: "done", endedAt: now } as Segment;
    }
    if (segment.kind === "text" && segment.status === "streaming") {
      return { ...segment, status: "done" } as Segment;
    }
    if (segment.kind === "tool" && segment.status === "running") {
      return {
        ...segment,
        status: status === "success" ? "success" : status,
        endedAt: now,
      } as Segment;
    }
    return segment;
  });
}

export function stringifyResult(content: unknown): string {
  if (typeof content === "string") return content;
  return JSON.stringify(content, null, 2);
}

