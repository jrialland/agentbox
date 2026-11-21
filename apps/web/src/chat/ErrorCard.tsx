import { Button } from "../design-system/primitives/Button";
import { StatusChip } from "../design-system/primitives/StatusChip";
import styles from "./chat.module.css";

export type RunError = { code?: string | number; message?: string };

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
  return (
    <div className={styles.errorCard} role="alert" data-testid={testId}>
      <div className={styles.errorHead}>
        <StatusChip tone="danger">{label}</StatusChip>
        {error.code !== undefined && (
          <code className={styles.errorCode}>{error.code}</code>
        )}
      </div>
      <p>{error.message ?? "The run failed."}</p>
      <Button variant="light" size="compact-sm" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}
