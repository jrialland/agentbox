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
  onClick,
}: {
  tone?: Tone;
  children: ReactNode;
  onClick?: () => void;
}) {
  return (
    <span
      className={styles.badge}
      data-tone={tone}
      onClick={onClick}
      style={onClick ? { cursor: "pointer" } : undefined}
    >
      {children}
    </span>
  );
}
