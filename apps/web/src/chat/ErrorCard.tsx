import { Button } from "../design-system/primitives/Button";
import { StatusChip } from "../design-system/primitives/StatusChip";
import styles from "./chat.module.css";

export type RunError = { code?: string | number; message?: string };

function friendlyMessage(message: string): string {
  if (/401|403|authentication fails|invalid.*api key/i.test(message)) {
    return "Provider authentication failed. Check the API key in Providers.";
  }
  if (/429|rate limit/i.test(message)) {
    return "The provider rate limit was reached. Wait a moment and retry.";
  }
  if (/timeout|timed out/i.test(message)) {
    return "The provider did not respond in time. Check the endpoint and retry.";
  }
  return message;
}

export function ErrorCard({
  error,
  onRetry,
  label = "run failed",
  testId = "error-card",
}: {
  error: RunError;
  onRetry: () => void;
  label?: string;
  testId?: string;
}) {
  const raw = error.message ?? "The run failed.";
  const friendly = friendlyMessage(raw);
  return (
    <div className={styles.errorCard} role="alert" data-testid={testId}>
      <div className={styles.errorHead}>
        <StatusChip tone="danger">{label}</StatusChip>
        {error.code !== undefined && (
          <code className={styles.errorCode}>{error.code}</code>
        )}
      </div>
      <p>{friendly}</p>
      {friendly !== raw && (
        <details className={styles.errorDetails}>
          <summary>Details</summary>
          <pre>{raw}</pre>
        </details>
      )}
      <Button variant="light" size="compact-sm" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}
