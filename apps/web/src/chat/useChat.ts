import { EventType } from "@ag-ui/core";
import type { AbstractAgent } from "@ag-ui/client";
import { useRef, useState } from "react";

import { createChatAgent, type SendOptions } from "./agent";
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
};

export function useChat(baseUrl: string, token: string | null, sessionId: string) {
  const [segments, setSegments] = useState<Segment[]>(emptySegments);
  const [appTabs, setAppTabs] = useState<AppTab[]>([]);
  const [running, setRunning] = useState(false);
  const [runStatus, setRunStatus] = useState<RunStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const agentRef = useRef<AbstractAgent | null>(null);
  const cancelRequested = useRef(false);

  function dispatch(event: RawEvent) {
    switch (event.type) {
      case EventType.TEXT_MESSAGE_START:
        setSegments((prev) =>
          applyAgUiEvent(prev, {
            type: "TEXT_MESSAGE_START",
            messageId: event.messageId ?? "",
          }),
        );
        break;
      case EventType.TEXT_MESSAGE_CONTENT:
        setSegments((prev) =>
          applyAgUiEvent(prev, {
            type: "TEXT_MESSAGE_CONTENT",
            messageId: event.messageId ?? "",
            delta: event.delta ?? "",
          }),
        );
        break;
      case EventType.TEXT_MESSAGE_END:
        setSegments((prev) =>
          applyAgUiEvent(prev, {
            type: "TEXT_MESSAGE_END",
            messageId: event.messageId ?? "",
          }),
        );
        break;
      case EventType.REASONING_MESSAGE_START:
        setSegments((prev) =>
          applyAgUiEvent(prev, {
            type: "REASONING_MESSAGE_START",
            messageId: event.messageId ?? "",
          }),
        );
        break;
      case EventType.REASONING_MESSAGE_CONTENT:
        setSegments((prev) =>
          applyAgUiEvent(prev, {
            type: "REASONING_MESSAGE_CONTENT",
            messageId: event.messageId ?? "",
            delta: event.delta ?? "",
          }),
        );
        break;
      case EventType.REASONING_MESSAGE_END:
        setSegments((prev) =>
          applyAgUiEvent(prev, {
            type: "REASONING_MESSAGE_END",
            messageId: event.messageId ?? "",
          }),
        );
        break;
      case EventType.TOOL_CALL_START:
        setSegments((prev) =>
          applyAgUiEvent(prev, {
            type: "TOOL_CALL_START",
            toolCallId: event.toolCallId ?? "",
            toolCallName: event.toolCallName ?? "tool",
          }),
        );
        break;
      case EventType.TOOL_CALL_ARGS:
        setSegments((prev) =>
          applyAgUiEvent(prev, {
            type: "TOOL_CALL_ARGS",
            toolCallId: event.toolCallId ?? "",
            delta: event.delta ?? "",
          }),
        );
        break;
      case EventType.TOOL_CALL_END:
        setSegments((prev) =>
          applyAgUiEvent(prev, {
            type: "TOOL_CALL_END",
            toolCallId: event.toolCallId ?? "",
          }),
        );
        break;
      case EventType.TOOL_CALL_RESULT:
        setSegments((prev) =>
          applyAgUiEvent(prev, {
            type: "TOOL_CALL_RESULT",
            toolCallId: event.toolCallId ?? "",
            content: event.content,
          }),
        );
        break;
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
    setRunning(true);
    setRunStatus("running");
    const agent = createChatAgent({ baseUrl, token, sessionId, send: opts });
    agentRef.current = agent;
    agent.subscribe({
      onEvent: ({ event }) => dispatch(event as RawEvent),
      onRunFailed: ({ error: runError }) => {
        setError(runError?.message ?? "Agent run failed");
        setSegments((prev) => finalizeSegments(prev, "error"));
        setRunning(false);
        setRunStatus("idle");
      },
      onRunErrorEvent: ({ event }) => {
        setError(event?.message ?? "run error");
        setSegments((prev) => finalizeSegments(prev, "error"));
        setRunning(false);
        setRunStatus("idle");
      },
    });
    agent.addMessage({ id: crypto.randomUUID(), role: "user", content });
    try {
      await agent.runAgent();
    } catch (e) {
      setError(String(e));
      setSegments((prev) => finalizeSegments(prev, "error"));
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
