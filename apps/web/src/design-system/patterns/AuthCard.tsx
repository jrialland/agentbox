import type { ReactNode } from "react";

import { Wordmark } from "../primitives/Wordmark";
import styles from "./patterns.module.css";

export function AuthCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div className={styles.authShell}>
      <div className={styles.authCard}>
        <Wordmark className={styles.authBrand} />
        <p className={styles.authStatus}>operator console · secure session</p>
        <h1>{title}</h1>
        {subtitle && <p className={styles.authSubtitle}>{subtitle}</p>}
        {children}
      </div>
    </div>
  );
}
