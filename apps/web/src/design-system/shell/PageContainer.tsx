import type { ReactNode } from "react";

import styles from "./shell.module.css";

export function PageContainer({
  children,
  fullBleed,
}: {
  children: ReactNode;
  fullBleed?: boolean;
}) {
  return (
    <div className={fullBleed ? styles.fullBleed : styles.container}>
      {children}
    </div>
  );
}
