import type { ReactNode } from "react";
import { useMatch } from "react-router-dom";

import { SESSION_ROUTE } from "../../routes";
import styles from "./shell.module.css";

export function Workspace({ children }: { children: ReactNode }) {
  const fullHeight = useMatch(SESSION_ROUTE) !== null;
  return (
    <main
      className={`${styles.workspace}${fullHeight ? ` ${styles.workspaceFullHeight}` : ""}`}
    >
      {children}
    </main>
  );
}
