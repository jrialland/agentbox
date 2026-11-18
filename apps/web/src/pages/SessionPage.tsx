import { Button, Select, Textarea } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { useMessages } from "../api/queries";
import { MarkdownBlock } from "../chat/MarkdownBlock";
import { ReasoningBlock } from "../chat/ReasoningBlock";
import { ToolCallBlock } from "../chat/ToolCallBlock";
import { useChat } from "../chat/useChat";
import { useAuthStore } from "../store/auth";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export function SessionPage() {
  const { id = "" } = useParams();
  const token = useAuthStore((s) => s.token);
  const { data: messages } = useMessages(id);
  const chat = useChat(API, token, id);
  const qc = useQueryClient();
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<string | null>("agent");

  async function onSend() {
    const content = input.trim();
    if (!content) return;
    setInput("");
    await chat.send(content, { mode: mode ?? "agent" });
    await qc.invalidateQueries({ queryKey: ["messages", id] });
  }

  return (
    <div>
      <h1 className="title">Session</h1>
      <div className="session-messages">
        {(messages ?? []).map((m) => (
          <div key={m.id} className={`session-turn session-turn-${m.role}`}>
            <p className="is-size-7 has-text-grey">{m.role}</p>
            {m.role === "assistant" ? (
              <MarkdownBlock content={m.content} />
            ) : (
              <pre className="session-content">{m.content}</pre>
            )}
          </div>
        ))}
        {(chat.text || chat.reasoning || chat.toolCalls.length > 0) && (
          <div className="session-turn session-turn-assistant">
            {chat.reasoning && <ReasoningBlock content={chat.reasoning} />}
            {chat.toolCalls.map((tc) => (
              <ToolCallBlock key={tc.id} call={tc} />
            ))}
            {chat.text && <MarkdownBlock content={chat.text} />}
          </div>
        )}
        {chat.error && <div className="notification is-danger">{chat.error}</div>}
      </div>
      <div className="box">
        <Textarea
          label="Message"
          value={input}
          onChange={(e) => setInput(e.currentTarget.value)}
          rows={3}
        />
        <div className="is-flex is-justify-content-space-between mt-2">
          <Select data={["ask", "agent"]} value={mode} onChange={setMode} w={120} />
          <Button onClick={onSend} loading={chat.running}>
            Send
          </Button>
        </div>
      </div>
    </div>
  );
}
