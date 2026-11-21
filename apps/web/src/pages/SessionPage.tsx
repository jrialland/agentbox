import { Button, Modal, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { RiChat3Line } from "@remixicon/react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { ApiError } from "../api/errors";
import { useMessages, useSession, useSessionLsp, useSessionPlan, useRenameSession } from "../api/queries";
import { AppPanel } from "../chat/AppPanel";
import { ChatSplit } from "../chat/ChatSplit";
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
import { ErrorState } from "../design-system/patterns/ErrorState";
import { EmptyState } from "../design-system/primitives/EmptyState";
import { PageContainer } from "../design-system/shell/PageContainer";
import { StatusChip } from "../design-system/primitives/StatusChip";
import { sessionTitle } from "../lib/sessionTitle";
import { useAuthStore } from "../store/auth";
import { SessionNotFound } from "./session/SessionNotFound";
import styles from "./session.module.css";

function duration(ms: number) {
  if (ms < 1) return "<1ms";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTokens(value: number) {
  return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : `${value}`;
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
      <details
        className={styles.reasoning}
        open={segment.status === "streaming"}
      >
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
  const sessionQuery = useSession(id);
  const notFound =
    sessionQuery.error instanceof ApiError && sessionQuery.error.status === 404;
  const sessionEnabled = sessionQuery.isSuccess && !notFound;
  const { data: session } = sessionQuery;
  const messagesQuery = useMessages(id, sessionEnabled);
  const lspQuery = useSessionLsp(id, sessionEnabled);
  const chat = useChat(API_URL, token, id);
  const planQuery = useSessionPlan(id, chat.running, sessionEnabled);
  const rename = useRenameSession();
  const { data: messages } = messagesQuery;
  const { data: lsp } = lspQuery;
  const { data: plan } = planQuery;
  const qc = useQueryClient();
  const [input, setInput] = useState("");
  const [pendingUser, setPendingUser] = useState<string | null>(null);
  const [mode, setMode] = useState<string | null>("agent");
  const [forkFromTurnId, setForkFromTurnId] = useState<string | null>(null);
  const [forkMode, setForkMode] = useState(false);
  const [skill, setSkill] = useState<string | null>(null);
  const [previousInput, setPreviousInput] = useState("");
  const [aboutOpen, setAboutOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
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
    await qc.invalidateQueries({ queryKey: ["sessions"] });
    await qc.invalidateQueries({ queryKey: ["session", id] });
    chat.reset();
  }

  async function saveTitle() {
    const title = titleDraft.trim();
    if (!title || rename.isPending) return;
    try {
      await rename.mutateAsync({ sid: id, title });
      setRenaming(false);
    } catch {
      notifications.show({ message: "Failed to rename session", color: "red" });
    }
  }

  async function handleSend(attachmentIds: string[]) {
    const content = input.trim();
    if (!content || chat.running) return;
    const doFork = forkMode;
    const forkFrom = forkFromTurnId;
    setInput("");
    setForkMode(false);
    setForkFromTurnId(null);
    setPendingUser(content);
    scrollToBottom();
    try {
      await chat.send(content, {
        mode: mode ?? "agent",
        fork: doFork,
        forkFromTurnId: forkFrom,
        attachmentIds,
        skill,
      });
      setSkill(null);
    } finally {
      setPendingUser(null);
      await refresh();
    }
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

  if (notFound) return <SessionNotFound />;
  if (sessionQuery.error) {
    return (
      <PageContainer>
        <ErrorState
          title="Could not load session"
          message={sessionQuery.error.message}
          onRetry={() => void sessionQuery.refetch()}
        />
      </PageContainer>
    );
  }

  const agentName = session?.agent_name ?? "";
  const contextTokens = [...(messages ?? [])]
    .reverse()
    .find((message) => message.role === "assistant" && message.context_tokens)
    ?.context_tokens;

  return (
    <PageContainer fullBleed>
      <div className={styles.session}>
        <ChatSplit
          appOpen={chat.appTabs.length > 0}
          chat={
            <div className={styles.main}>
          <div className={styles.header} data-testid="session-agent">
            {agentName && <AgentAvatar name={agentName} />}
            <span>{agentName || "Agent"}</span>
            <Button size="compact-xs" variant="light" onClick={() => setAboutOpen(true)}>
              About
            </Button>
            <h1>{sessionTitle(session?.title)}</h1>
            {contextTokens ? (
              <span
                className={styles.contextUsage}
                title="Context tokens after the last completed turn"
              >
                {formatTokens(contextTokens)} tokens
              </span>
            ) : null}
            <Button
              size="compact-xs"
              variant="light"
              onClick={() => {
                setTitleDraft(session?.title ?? "");
                setRenaming(true);
              }}
            >
              Rename
            </Button>
            {renaming && (
              <>
                <TextInput
                  aria-label="Session title"
                  className={styles.titleInput}
                  size="xs"
                  maxLength={120}
                  value={titleDraft}
                  onChange={(event) => setTitleDraft(event.currentTarget.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void saveTitle();
                    if (event.key === "Escape") setRenaming(false);
                  }}
                  autoFocus
                />
                <Button size="compact-xs" onClick={() => void saveTitle()}>
                  Save title
                </Button>
                <Button
                  size="compact-xs"
                  variant="light"
                  onClick={() => setRenaming(false)}
                >
                  Cancel
                </Button>
              </>
            )}
          </div>
          {planQuery.error ? (
            <ErrorCard
              label="plan unavailable"
              error={{ message: planQuery.error.message }}
              onRetry={() => void planQuery.refetch()}
              testId="plan-error"
            />
          ) : (
            <PlanPanel items={plan?.items ?? []} />
          )}
          <div className={styles.messages} ref={messagesRef} data-testid="messages">
            {!messagesQuery.error &&
              !messagesQuery.isLoading &&
              (messages ?? []).length === 0 &&
              chat.segments.length === 0 &&
              !chat.running && (
                <div className={styles.emptySession}>
                  <EmptyState
                    icon={RiChat3Line}
                    title="Start the conversation"
                    description="Ask a question, type / for skills, or @ to reference a project file."
                  />
                </div>
              )}
            {pendingUser && (
              <MessageTurn
                message={{ id: "pending-user", role: "user", content: pendingUser }}
                agentName={agentName || "Agent"}
                sessionId={id}
              />
            )}
            {messagesQuery.error ? (
              <ErrorCard
                label="messages unavailable"
                error={{ message: messagesQuery.error.message }}
                onRetry={() => void messagesQuery.refetch()}
                testId="messages-error"
              />
            ) : (
              (messages ?? []).map((message) =>
                message.role === "summary" ? (
                  <SummaryNotice key={message.id} content={message.content} />
                ) : (
                  <MessageTurn
                    key={message.id}
                    message={message as ChatMessage}
                    agentName={agentName || "Agent"}
                    sessionId={id}
                    onRetry={retry}
                    onEdit={(message) => {
                      setPreviousInput(input);
                      setInput(message.content);
                      setForkMode(true);
                      setForkFromTurnId(message.parent_id ?? null);
                    }}
                  />
                ),
              )
            )}
            {chat.segments.length > 0 && (
              <div className={styles.liveTurn} data-testid="live-turn">
                {chat.segments.map((segment) => (
                  <div key={segment.id} data-segment={segment.kind}>
                    <LiveSegment segment={segment} />
                  </div>
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
          }
          app={<AppPanel sessionId={id} tabs={chat.appTabs} onClose={chat.closeApp} />}
        />
      </div>
      <Modal
        opened={aboutOpen}
        onClose={() => setAboutOpen(false)}
        title="About this session"
      >
        {lspQuery.error ? (
          <ErrorCard
            label="language servers unavailable"
            error={{ message: lspQuery.error.message }}
            onRetry={() => void lspQuery.refetch()}
            testId="lsp-error"
          />
        ) : (
          <>
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
          </>
        )}
      </Modal>
    </PageContainer>
  );
}



