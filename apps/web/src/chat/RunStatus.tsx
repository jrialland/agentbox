import { Button } from "../design-system/primitives/Button";
import { Spinner } from "../design-system/primitives/Spinner";
import styles from "./chat.module.css";

export function RunStatus({
  running,
  elapsedMs,
  onStop,
}: {
  running: boolean;
  elapsedMs: number;
  onStop: () => void;
}) {
  if (!running) return null;

  return (
    <div className={styles.runStatus} role="status">
      <Spinner label="Agent running" />
      <span>Thinking.</span>
      <span className={styles.elapsed}>{(elapsedMs / 1000).toFixed(1)}s</span>
      <Button variant="light" size="compact-sm" onClick={onStop}>
        Stop
      </Button>
    </div>
  );
}
