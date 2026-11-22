import styles from "./primitives.module.css";

export function Wordmark({ className }: { className?: string }) {
  return (
    <span role="img" aria-label="Agentbox" className={className}>
      [AGENTBOX]<span aria-hidden className={styles.brandCursor}>▮</span>
    </span>
  );
}
