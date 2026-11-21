import { notifications } from "@mantine/notifications";
import { EventType } from "@ag-ui/core";
import { useRef, useState } from "react";

import { streamChat, type SendOptions } from "./agent";
import { appTabFromSnapshot, type AppTab } from "./apps";
import {
  applyAgUiEvent,
  emptySegments,
  finalizeSegments,
  type Segment,
} from "./segments";

type RunStatus = "idle" | "running" | "cancelling";

type RawEvent = {
  type: EventType;
  messageId?: string;
  delta?: string;
  toolCallId?: string;
  toolCallName?: string;
  content?: unknown;
  activityType?: string;
  message?: string;
  name?: string;
  value?: unknown;
};

export function useChat(baseUrl: string, token: string | null, sessionId: string) {
  const [segments, setSegments] = useState<Segment[]>(emptySegments);
  const [appTabs, setAppTabs] = useState<AppTab[]>([]);
  const [running, setRunning] = useState(false);
  const [runStatus, setRunStatus] = useState<RunStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const cancelRequested = useRef(false);
  const textIdRef = useRef<string | null>(null);
  const reasoningIdRef = useRef<string | null>(null);
  const toolIdRef = useRef<string | null>(null);

  function appendText(event: RawEvent) {
    const id = event.messageId || textIdRef.current || crypto.randomUUID();
    textIdRef.current = id;
    setSegments((prev) => {
      let next = prev.some((segment) => segment.id === id)
        ? prev
        : applyAgUiEvent(prev, { type: "TEXT_MESSAGE_START", messageId: id });
      if (event.delta) {
        next = applyAgUiEvent(next, {
          type: "TEXT_MESSAGE_CONTENT",
          messageId: id,
          delta: event.delta,
        });
      }
      return next;
    });
  }

  function appendReasoning(event: RawEvent) {
    const id = event.messageId || reasoningIdRef.current || crypto.randomUUID();
    reasoningIdRef.current = id;
    setSegments((prev) => {
      let next = prev.some((segment) => segment.id === id)
        ? prev
        : applyAgUiEvent(prev, { type: "REASONING_MESSAGE_START", messageId: id });
      if (event.delta) {
        next = applyAgUiEvent(next, {
          type: "REASONING_MESSAGE_CONTENT",
          messageId: id,
          delta: event.delta,
        });
      }
      return next;
    });
  }

  function appendTool(event: RawEvent) {
    const id = event.toolCallId || toolIdRef.current || crypto.randomUUID();
    toolIdRef.current = id;
    setSegments((prev) => {
      const existing = prev.find((segment) => segment.id === id);
      let next = existing
        ? prev
        : applyAgUiEvent(prev, {
            type: "TOOL_CALL_START",
            toolCallId: id,
            toolCallName: event.toolCallName ?? "tool",
          });
      if (event.delta) {
        next = applyAgUiEvent(next, {
          type: "TOOL_CALL_ARGS",
          toolCallId: id,
          delta: event.delta,
        });
      }
      return next;
    });
  }

  function dispatch(event: RawEvent) {
    switch (event.type) {
      case EventType.TEXT_MESSAGE_START:
        appendText({ ...event, delta: "" });
        break;
      case EventType.TEXT_MESSAGE_CONTENT:
      case EventType.TEXT_MESSAGE_CHUNK:
        appendText(event);
        break;
      case EventType.TEXT_MESSAGE_END: {
        const id = event.messageId || textIdRef.current;
        if (id) {
          setSegments((prev) =>
            applyAgUiEvent(prev, { type: "TEXT_MESSAGE_END", messageId: id }),
          );
        }
        if (!event.messageId || event.messageId === textIdRef.current) {
          textIdRef.current = null;
        }
        break;
      }
      case EventType.REASONING_MESSAGE_START:
        appendReasoning({ ...event, delta: "" });
        break;
      case EventType.REASONING_MESSAGE_CONTENT:
      case EventType.REASONING_MESSAGE_CHUNK:
        appendReasoning(event);
        break;
      case EventType.REASONING_MESSAGE_END: {
        const id = event.messageId || reasoningIdRef.current;
        if (id) {
          setSegments((prev) =>
            applyAgUiEvent(prev, {
              type: "REASONING_MESSAGE_END",
              messageId: id,
            }),
          );
        }
        if (!event.messageId || event.messageId === reasoningIdRef.current) {
          reasoningIdRef.current = null;
        }
        break;
      }
      case EventType.TOOL_CALL_START:
        appendTool({ ...event, delta: "" });
        break;
      case EventType.TOOL_CALL_ARGS:
      case EventType.TOOL_CALL_CHUNK:
        appendTool(event);
        break;
      case EventType.TOOL_CALL_END: {
        const id = event.toolCallId || toolIdRef.current;
        if (id) {
          setSegments((prev) =>
            applyAgUiEvent(prev, { type: "TOOL_CALL_END", toolCallId: id }),
          );
        }
        break;
      }
      case EventType.TOOL_CALL_RESULT: {
        const id = event.toolCallId || toolIdRef.current || "";
        setSegments((prev) =>
          applyAgUiEvent(prev, {
            type: "TOOL_CALL_RESULT",
            toolCallId: id,
            content: event.content,
          }),
        );
        break;
      }
      case EventType.ACTIVITY_SNAPSHOT: {
        const tab = appTabFromSnapshot({
          messageId: event.messageId ?? "",
          activityType: event.activityType ?? "",
          content: (event.content as Record<string, unknown>) ?? {},
        });
        if (tab) {
          setAppTabs((prev) =>
            prev.some((item) => item.id === tab.id) ? prev : [...prev, tab],
          );
          setSegments((prev) =>
            applyAgUiEvent(prev, {
              type: "ACTIVITY_SNAPSHOT",
              messageId: event.messageId ?? "",
              tab,
            }),
          );
        }
        break;
      }
      case EventType.CUSTOM: {
        if (event.name === "mcp.warning") {
          const payload = (event.value ?? {}) as { server?: string; message?: string };
          notifications.show({
            title: `MCP server: ${payload.server ?? "unknown"}`,
            message: payload.message ?? "Server unavailable",
            color: "yellow",
          });
        }
        break;
      }
      case EventType.RUN_ERROR:
        setError(event.message ?? "run error");
        setSegments((prev) => finalizeSegments(prev, "error"));
        setRunning(false);
        setRunStatus("idle");
        break;
      case EventType.RUN_FINISHED:
        setSegments((prev) =>
          finalizeSegments(prev, cancelRequested.current ? "cancelled" : "success"),
        );
        cancelRequested.current = false;
        setRunning(false);
        setRunStatus("idle");
        break;
      default:
        break;
    }
  }

  async function send(content: string, opts: SendOptions) {
    setSegments(emptySegments());
    setError(null);
    cancelRequested.current = false;
    textIdRef.current = null;
    reasoningIdRef.current = null;
    toolIdRef.current = null;
    setRunning(true);
    setRunStatus("running");
    try {
      for await (const event of streamChat({
        baseUrl,
        token,
        sessionId,
        send: opts,
        content,
      })) {
        dispatch(event as RawEvent);
      }
      setSegments((prev) =>
        finalizeSegments(prev, cancelRequested.current ? "cancelled" : "success"),
      );
    } catch (e) {
      setError((current) => current ?? String(e));
      setSegments((prev) => finalizeSegments(prev, "error"));
    } finally {
      setRunning(false);
      setRunStatus("idle");
    }
  }
  async function cancel() {
    cancelRequested.current = true;
    setRunStatus("cancelling");
    await fetch(`${baseUrl}/sessions/${sessionId}/messages/cancel`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  }

  function reset() {
    setSegments(emptySegments());
    setError(null);
    textIdRef.current = null;
    reasoningIdRef.current = null;
    toolIdRef.current = null;
  }

  function closeApp(id: string) {
    setAppTabs((prev) => prev.filter((tab) => tab.id !== id));
  }

  return {
    segments,
    appTabs,
    running,
    runStatus,
    error,
    send,
    cancel,
    reset,
    closeApp,
  };
}





