import type { AbstractAgent } from "@ag-ui/client";
import { useRef, useState } from "react";

import { createChatAgent, type SendOptions } from "./agent";

export type ToolCall = { id: string; name: string; args: string; result?: string };

export function useChat(baseUrl: string, token: string | null, sessionId: string) {
  const [text, setText] = useState("");
  const [reasoning, setReasoning] = useState("");
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const agentRef = useRef<AbstractAgent | null>(null);

  async function send(content: string, opts: SendOptions) {
    setText("");
    setReasoning("");
    setToolCalls([]);
    setError(null);
    setRunning(true);
    const agent = createChatAgent({ baseUrl, token, sessionId, send: opts });
    agentRef.current = agent;
    agent.addMessage({ id: crypto.randomUUID(), role: "user", content });
    try {
      await agent.runAgent(undefined, {
        onTextMessageContentEvent: (p: { textMessageBuffer: string }) =>
          setText(p.textMessageBuffer),
        onReasoningMessageContentEvent: (p: { reasoningMessageBuffer: string }) =>
          setReasoning(p.reasoningMessageBuffer),
        onToolCallStartEvent: (p: { event: { toolCallId: string; toolCallName: string } }) =>
          setToolCalls((prev) => [
            ...prev,
            { id: p.event.toolCallId, name: p.event.toolCallName, args: "" },
          ]),
        onToolCallEndEvent: (p: {
          event: { toolCallId: string };
          toolCallArgs: Record<string, unknown>;
        }) =>
          setToolCalls((prev) =>
            prev.map((tc) =>
              tc.id === p.event.toolCallId
                ? { ...tc, args: JSON.stringify(p.toolCallArgs) }
                : tc,
            ),
          ),
        onToolCallResultEvent: (p: { event: { toolCallId: string; content: unknown } }) =>
          setToolCalls((prev) =>
            prev.map((tc) =>
              tc.id === p.event.toolCallId
                ? { ...tc, result: String(p.event.content) }
                : tc,
            ),
          ),
        onRunErrorEvent: (p: { event: { message?: string } }) =>
          setError(p.event?.message ?? "run error"),
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  }

  function reset() {
    setText("");
    setReasoning("");
    setToolCalls([]);
  }

  return { text, reasoning, toolCalls, running, error, send, reset };
}
