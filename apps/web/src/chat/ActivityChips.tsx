import { Badge, type Tone } from "../design-system/primitives/Badge";
import { StatusChip } from "../design-system/primitives/StatusChip";
import styles from "./chat.module.css";

export type ToolActivitySummary = {
  name: string;
  status: string;
  duration_ms: number;
  args?: string;
  result?: string;
};

export type ActivitySummary = {
  status?: string;
  reasoning_ms?: number;
  reasoning_text?: string;
  tools?: ToolActivitySummary[];
  error?: { code?: number; message?: string } | null;
};

function duration(ms: number): string {
  if (ms < 1) return "<1ms";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function tone(status: string): Tone {
  if (status === "success") return "success";
  if (status === "error") return "danger";
  if (status === "cancelled") return "warning";
  return "neutral";
}

export function ActivityChips({
  activity,
  defaultOpen = false,
}: {
  activity: ActivitySummary;
  defaultOpen?: boolean;
}) {
  const tools = activity.tools ?? [];
  const reasoning = activity.reasoning_ms ?? 0;
  if (reasoning <= 0 && tools.length === 0) return null;

  return (
    <details className={styles.activity} open={defaultOpen}>
      <summary>
        <span className={styles.activityLabel}>Activity</span>
        {reasoning > 0 && <Badge tone="info">Reasoning {duration(reasoning)}</Badge>}
        {tools.length > 0 && (
          <Badge tone="neutral">
            {tools.length} {tools.length === 1 ? "tool" : "tools"}
          </Badge>
        )}
      </summary>
      <ul className={styles.activityList}>
        {reasoning > 0 && (
          <li>
            <span>Reasoning</span>
            <StatusChip tone="info">done</StatusChip>
            <span className={styles.duration}>{duration(reasoning)}</span>
          </li>
        )}
        {tools.map((tool, index) => (
          <li key={`${tool.name}-${index}`}>
            <code>{tool.name}</code>
            <StatusChip tone={tone(tool.status)}>{tool.status}</StatusChip>
            <span className={styles.duration}>{duration(tool.duration_ms)}</span>
          </li>
        ))}
      </ul>
      {reasoning > 0 && activity.reasoning_text && (
        <details className={styles.toolDetails}>
          <summary>Reasoning text</summary>
          <pre>{activity.reasoning_text}</pre>
        </details>
      )}
      {tools.map((tool, index) =>
        tool.args || tool.result ? (
          <details
            key={`${tool.name}-details-${index}`}
            className={styles.toolDetails}
          >
            <summary>
              <code>{tool.name}</code> details
            </summary>
            {tool.args && <pre>{tool.args}</pre>}
            {tool.result && <pre>{tool.result}</pre>}
          </details>
        ) : null,
      )}
    </details>
  );
}


