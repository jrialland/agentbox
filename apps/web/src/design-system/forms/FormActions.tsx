import type { ReactNode } from "react";

import styles from "./forms.module.css";

export function FormActions({ children }: { children: ReactNode }) {
  return <div className={styles.actions}>{children}</div>;
}
