import type { ReactNode } from "react";

import styles from "./primitives.module.css";

export function Toolbar({
  children,
  align = "space-between",
}: {
  children: ReactNode;
  align?: "start" | "space-between";
}) {
  return (
    <div className={styles.toolbar} data-align={align}>
      {children}
    </div>
  );
}
