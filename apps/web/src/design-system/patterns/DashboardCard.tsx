import type { ReactNode } from "react";

import styles from "./patterns.module.css";

export function DashboardCard({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  icon?: ReactNode;
}) {
  return (
    <div className={styles.dashboardCard}>
      <div className={styles.dashboardCardTop}>
        <span>{label}</span>
        {icon}
      </div>
      <strong>{value}</strong>
      {hint && <small>{hint}</small>}
    </div>
  );
}
