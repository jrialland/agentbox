import type { ReactNode } from "react";

import styles from "./data.module.css";

export function ListRow({
  title,
  subtitle,
  meta,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className={styles.listRow}>
      <div className={styles.listRowMain}>
        <strong>{title}</strong>
        {subtitle && <span>{subtitle}</span>}
      </div>
      {meta && <div className={styles.listRowMeta}>{meta}</div>}
      {actions && <div className={styles.listRowActions}>{actions}</div>}
    </div>
  );
}
