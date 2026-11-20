import type { ReactNode } from "react";

import styles from "./data.module.css";

export function TableToolbar({ children }: { children: ReactNode }) {
  return <div className={styles.tableToolbar}>{children}</div>;
}
