import type { ReactNode } from "react";

import styles from "./shell.module.css";

export function Workspace({ children }: { children: ReactNode }) {
  return <main className={styles.workspace}>{children}</main>;
}
