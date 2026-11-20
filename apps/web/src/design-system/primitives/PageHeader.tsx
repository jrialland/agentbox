import type { ReactNode } from "react";

import styles from "./primitives.module.css";

export function PageHeader({
  title,
  subtitle,
  breadcrumbs,
  actions,
}: {
  title: string;
  subtitle?: string;
  breadcrumbs?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className={styles.pageHeader}>
      {breadcrumbs && <div className={styles.breadcrumbs}>{breadcrumbs}</div>}
      <div className={styles.pageHeaderRow}>
        <div>
          <h1 className={styles.pageTitle}>{title}</h1>
          {subtitle && <p className={styles.pageSubtitle}>{subtitle}</p>}
        </div>
        {actions && <div className={styles.pageActions}>{actions}</div>}
      </div>
    </header>
  );
}
