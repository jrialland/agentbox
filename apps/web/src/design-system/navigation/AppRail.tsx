import type { ReactNode } from "react";

import styles from "./navigation.module.css";

export function AppRail({
  children,
  footer,
}: {
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <nav className={styles.rail} aria-label="Primary navigation">
      <div className={styles.railBrand} aria-label="Agentbox">
        [A]
      </div>
      <div className={styles.railItems}>{children}</div>
      <div className={styles.railFooter}>{footer}</div>
    </nav>
  );
}
