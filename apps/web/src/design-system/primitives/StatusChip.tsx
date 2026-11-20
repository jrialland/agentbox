import type { ReactNode } from "react";

import type { Tone } from "./Badge";
import styles from "./primitives.module.css";

export function StatusChip({
  tone = "neutral",
  children,
}: {
  tone?: Tone;
  children: ReactNode;
}) {
  return (
    <span className={styles.statusChip} data-tone={tone}>
      <span className={styles.statusDot} />
      {children}
    </span>
  );
}
