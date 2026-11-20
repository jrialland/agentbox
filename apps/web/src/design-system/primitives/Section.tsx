import type { ReactNode } from "react";

import styles from "./primitives.module.css";

export function Section({
  title,
  children,
}: {
  title?: string;
  children: ReactNode;
}) {
  return (
    <section className={styles.section}>
      {title && <h2 className={styles.sectionTitle}>{title}</h2>}
      {children}
    </section>
  );
}
