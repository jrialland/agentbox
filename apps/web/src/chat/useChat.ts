import type { AbstractAgent } from "@ag-ui/client";
import { useRef, useState } from "react";

import { createChatAgent, type SendOptions } from "./agent";

export function useChat(baseUrl: string, token: string | null, sessionId: string) {
  const [text, setText] = useState("");
  const [reasoning, setReasoning] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const agentRef = useRef<AbstractAgent | null>(null);

  async function send(content: string, opts: SendOptions) {
    setText("");
    setReasoning("");
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
        onRunErrorEvent: (p: { event: { message?: string } }) =>
          setError(p.event?.message ?? "run error"),
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  }

  return { text, reasoning, running, error, send };
}
