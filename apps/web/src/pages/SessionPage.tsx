import { Button, Modal } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { useMessages, useSession, useSessionLsp, useSessionPlan } from "../api/queries";
import { AppPanel } from "../chat/AppPanel";
import "../chat/apps.css";
import { Composer } from "../chat/Composer";
import { MarkdownBlock } from "../chat/MarkdownBlock";
import { PlanPanel } from "../chat/PlanPanel";
import { ReasoningBlock } from "../chat/ReasoningBlock";
import { ToolCallBlock } from "../chat/ToolCallBlock";
import { useChat } from "../chat/useChat";
import { AgentAvatar } from "../components/agents/AgentAvatar";
import { API_URL } from "../config";
import { useAuthStore } from "../store/auth";

export function SessionPage() {
  const { id = "" } = useParams();
  const token = useAuthStore((s) => s.token);
  const { data: messages } = useMessages(id);
  const { data: session } = useSession(id);
  const { data: lsp } = useSessionLsp(id);
  const chat = useChat(API_URL, token, id);
  const { data: plan } = useSessionPlan(id, chat.running);
  const qc = useQueryClient();
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<string | null>("agent");
  const [forkFromTurnId, setForkFromTurnId] = useState<string | null>(null);
  const [forkMode, setForkMode] = useState(false);
  const [skill, setSkill] = useState<string | null>(null);
  const [aboutOpen, setAboutOpen] = useState(false);

  async function handleSend(attachmentIds: string[]) {
    const content = input.trim();
    if (!content) return;
    const doFork = forkMode;
    const forkFrom = forkFromTurnId;
    setInput("");
    setForkMode(false);
    setForkFromTurnId(null);
    await chat.send(content, {
      mode: mode ?? "agent",
      fork: doFork,
      forkFromTurnId: forkFrom,
      attachmentIds,
      skill,
    });
    setSkill(null);
    await qc.refetchQueries({ queryKey: ["messages", id] });
    await qc.invalidateQueries({ queryKey: ["session-plan", id] });
    chat.reset();
  }

  return (
    <div className={chat.appTabs.length > 0 ? "session-layout" : undefined}>
      <div className={chat.appTabs.length > 0 ? "session-main" : "session-full"}>
        {session && (
          <div
            className="is-flex is-align-items-center"
            style={{ gap: 8, marginBottom: "0.75rem" }}
            data-testid="session-agent"
          >
            <AgentAvatar name={session.agent_name} />
            <span className="has-text-weight-semibold">{session.agent_name}</span>
            <Button
              size="compact-xs"
              variant="light"
              onClick={() => setAboutOpen(true)}
            >
              About
            </Button>
          </div>
        )}
        <h1 className="title">Session</h1>
        <PlanPanel items={plan?.items ?? []} />
        <div className="session-messages">
          {(messages ?? []).map((m) => (
            <div key={m.id} className={`session-turn session-turn-${m.role}`}>
              <div className="is-flex is-justify-content-space-between">
                <p className="is-size-7 has-text-grey">{m.role}</p>
                {m.role === "user" && (
                  <Button
                    size="compact-xs"
                    variant="subtle"
                    onClick={() => {
                      setInput(m.content);
                      setForkMode(true);
                      setForkFromTurnId(m.parent_id ?? null);
                    }}
                  >
                    Edit
                  </Button>
                )}
              </div>
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
        <Composer
          sessionId={id}
          value={input}
          setValue={setInput}
          mode={mode}
          setMode={setMode}
          running={chat.running}
          onSend={handleSend}
          onSelectSkill={(name) => setSkill(name)}
        />
      </div>
      {chat.appTabs.length > 0 && (
        <AppPanel sessionId={id} tabs={chat.appTabs} onClose={chat.closeApp} />
      )}
      <Modal
        opened={aboutOpen}
        onClose={() => setAboutOpen(false)}
        title="About this session"
      >
        <p className="has-text-weight-semibold">Detected stacks</p>
        <ul>
          {(lsp?.detected ?? []).map((name) => (
            <li key={name}>{name}</li>
          ))}
        </ul>
        <p className="has-text-weight-semibold">Active language servers</p>
        {lsp && lsp.active.length > 0 ? (
          <ul>
            {lsp.active.map((server) => (
              <li key={server.stack}>
                {server.stack} — {server.status} ({server.documents} docs)
                <br />
                <code>{server.command}</code>
              </li>
            ))}
          </ul>
        ) : (
          <p>No active language servers yet.</p>
        )}
      </Modal>
    </div>
  );
}
