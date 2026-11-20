import type { ReactNode } from "react";

import styles from "./primitives.module.css";

export type Tone =
  | "neutral"
  | "success"
  | "warning"
  | "info"
  | "danger"
  | "agent";

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: Tone;
  children: ReactNode;
}) {
  return (
    <span className={styles.badge} data-tone={tone}>
      {children}
    </span>
  );
}
