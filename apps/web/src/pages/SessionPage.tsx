import { Button, Modal } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { useMessages, useSession, useSessionLsp, useSessionPlan } from "../api/queries";
import "../chat/apps.css";
import { AppPanel } from "../chat/AppPanel";
import { Composer } from "../chat/Composer";
import { ErrorCard } from "../chat/ErrorCard";
import { ForkBanner } from "../chat/ForkBanner";
import { MarkdownBlock } from "../chat/MarkdownBlock";
import { MessageTurn, type ChatMessage } from "../chat/MessageTurn";
import { PlanPanel } from "../chat/PlanPanel";
import { RunStatus } from "../chat/RunStatus";
import type { Segment } from "../chat/segments";
import { SummaryNotice } from "../chat/SummaryNotice";
import { useAutoScroll } from "../chat/useAutoScroll";
import { useChat } from "../chat/useChat";
import { AgentAvatar } from "../components/agents/AgentAvatar";
import { API_URL } from "../config";
import { PageContainer } from "../design-system/shell/PageContainer";
import { StatusChip } from "../design-system/primitives/StatusChip";
import { useAuthStore } from "../store/auth";
import styles from "./session.module.css";

function duration(ms: number) {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function toolTone(status: string): "success" | "danger" | "warning" | "neutral" {
  if (status === "success") return "success";
  if (status === "error") return "danger";
  if (status === "cancelled") return "warning";
  return "neutral";
}

function LiveSegment({ segment }: { segment: Segment }) {
  if (segment.kind === "text") {
    return <MarkdownBlock content={segment.text} />;
  }
  if (segment.kind === "reasoning") {
    const elapsed = segment.endedAt ? segment.endedAt - segment.startedAt : 0;
    return (
      <details className={styles.reasoning}>
        <summary>
          {segment.status === "streaming" ? "Thinking." : `Thought ${duration(elapsed)}`}
        </summary>
        <pre>{segment.text}</pre>
      </details>
    );
  }
  if (segment.kind === "tool") {
    const elapsed = segment.endedAt ? segment.endedAt - segment.startedAt : 0;
    return (
      <div className={styles.toolCard}>
        <div className={styles.toolHead}>
          <code>{segment.name}</code>
          <StatusChip tone={toolTone(segment.status)}>{segment.status}</StatusChip>
          <span className={styles.toolDuration}>
            {segment.status === "running" ? "running" : duration(elapsed)}
          </span>
        </div>
        {(segment.args || segment.result) && (
          <details className={styles.toolDetails}>
            <summary>Details</summary>
            {segment.args && <pre>{segment.args}</pre>}
            {segment.result && <pre>{segment.result}</pre>}
          </details>
        )}
      </div>
    );
  }
  return <p className={styles.appSegment}>MCP app opened in the app panel.</p>;
}

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
  const [previousInput, setPreviousInput] = useState("");
  const [aboutOpen, setAboutOpen] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const startedAt = useRef<number | null>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const { atBottom, scrollToBottom } = useAutoScroll(messagesRef, [
    messages?.length,
    chat.segments,
  ]);

  useEffect(() => {
    if (!chat.running) {
      startedAt.current = null;
      setElapsed(0);
      return;
    }
    startedAt.current = Date.now();
    const timer = window.setInterval(() => {
      if (startedAt.current) setElapsed(Date.now() - startedAt.current);
    }, 250);
    return () => window.clearInterval(timer);
  }, [chat.running]);

  async function refresh() {
    await qc.refetchQueries({ queryKey: ["messages", id] });
    await qc.invalidateQueries({ queryKey: ["session-plan", id] });
    chat.reset();
  }

  async function handleSend(attachmentIds: string[]) {
    const content = input.trim();
    if (!content || chat.running) return;
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
    await refresh();
  }

  function userTurnFor(messageId: string) {
    const failed = (messages ?? []).find((message) => message.id === messageId);
    if (!failed) return null;
    if (failed.role === "user") return failed;
    return (messages ?? []).find((message) => message.id === failed.parent_id) ?? null;
  }

  async function retry(messageId: string) {
    if (chat.running) return;
    const userTurn = userTurnFor(messageId) as ChatMessage | null;
    const content = userTurn?.content ?? "";
    if (!content.trim()) return;
    await chat.send(content, {
      mode: mode ?? "agent",
      retryTurnId: messageId,
      attachmentIds: (userTurn?.attachments ?? []).map(
        (attachment: { id: string }) => attachment.id,
      ),
    });
    await refresh();
  }

  const agentName = session?.agent_name ?? "Agent";

  return (
    <PageContainer fullBleed>
      <div className={styles.session}>
        <div className={styles.main}>
          <div className={styles.header} data-testid="session-agent">
            <AgentAvatar name={agentName} />
            <span>{agentName}</span>
            <Button size="compact-xs" variant="light" onClick={() => setAboutOpen(true)}>
              About
            </Button>
            <h1>Session</h1>
          </div>
          <PlanPanel items={plan?.items ?? []} />
          <div className={styles.messages} ref={messagesRef}>
            {(messages ?? []).map((message) =>
              message.role === "summary" ? (
                <SummaryNotice key={message.id} content={message.content} />
              ) : (
                <MessageTurn
                  key={message.id}
                  message={message as ChatMessage}
                  agentName={agentName}
                  sessionId={id}
                  onRetry={retry}
                />
              ),
            )}
            {chat.segments.length > 0 && (
              <div className={styles.liveTurn}>
                {chat.segments.map((segment) => (
                  <LiveSegment key={segment.id} segment={segment} />
                ))}
              </div>
            )}
            {chat.error && (
              <ErrorCard error={{ message: chat.error }} onRetry={() => {}} />
            )}
            {!atBottom && (
              <div className={styles.jump}>
                <Button size="compact-sm" variant="light" onClick={scrollToBottom}>
                  Jump to latest
                </Button>
              </div>
            )}
          </div>
          <RunStatus
            running={chat.running}
            elapsedMs={elapsed}
            onStop={() => void chat.cancel()}
          />
          {forkMode && (
            <ForkBanner
              onCancel={() => {
                setInput(previousInput);
                setForkMode(false);
                setForkFromTurnId(null);
              }}
            />
          )}
          <Composer
            sessionId={id}
            value={input}
            setValue={setInput}
            mode={mode}
            setMode={setMode}
            running={chat.running}
            onSend={handleSend}
            onStop={() => void chat.cancel()}
            onSelectSkill={(name) => setSkill(name)}
          />
        </div>
        {chat.appTabs.length > 0 && (
          <div className={styles.split}>
            <AppPanel sessionId={id} tabs={chat.appTabs} onClose={chat.closeApp} />
          </div>
        )}
      </div>
      <Modal
        opened={aboutOpen}
        onClose={() => setAboutOpen(false)}
        title="About this session"
      >
        <p>Detected stacks</p>
        <ul>
          {(lsp?.detected ?? []).map((name) => (
            <li key={name}>{name}</li>
          ))}
        </ul>
        <p>Active language servers</p>
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
    </PageContainer>
  );
}
