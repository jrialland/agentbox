import { StatusChip } from "../design-system/primitives/StatusChip";
import { ActivityChips, type ActivitySummary } from "./ActivityChips";
import { AttachmentChip, type AttachmentMeta } from "./AttachmentChip";
import styles from "./chat.module.css";
import { MarkdownBlock } from "./MarkdownBlock";

export type ChatMessage = {
  id: string;
  role: string;
  content: string;
  parent_id?: string | null;
  created_at?: string;
  activity?: ActivitySummary | null;
  attachments?: AttachmentMeta[] | null;
};

export function MessageTurn({
  message,
  agentName,
  sessionId,
}: {
  message: ChatMessage;
  agentName: string;
  sessionId: string;
}) {
  const isUser = message.role === "user";
  const status = message.activity?.status;

  return (
    <article
      className={`${styles.turn} ${isUser ? styles.userTurn : styles.assistantTurn}`}
      data-role={message.role}
    >
      <header className={styles.turnHeader}>
        <span className={styles.role}>{isUser ? "You" : agentName}</span>
        {status === "cancelled" && <StatusChip tone="warning">cancelled</StatusChip>}
        {status === "error" && <StatusChip tone="danger">error</StatusChip>}
      </header>
      {isUser ? (
        <p className={styles.userText}>{message.content}</p>
      ) : (
        message.content && <MarkdownBlock content={message.content} />
      )}
      {message.attachments && message.attachments.length > 0 && (
        <div className={styles.attachments}>
          {message.attachments.map((attachment) => (
            <AttachmentChip
              key={attachment.id}
              attachment={attachment}
              sessionId={sessionId}
            />
          ))}
        </div>
      )}
      {!isUser && message.activity && <ActivityChips activity={message.activity} />}
    </article>
  );
}
