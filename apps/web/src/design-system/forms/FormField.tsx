import type { ReactNode } from "react";

import styles from "./forms.module.css";

export function FormField({
  label,
  description,
  error,
  required,
  children,
}: {
  label: string;
  description?: string;
  error?: string | null;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <label className={styles.field}>
      <span className={styles.label}>
        {label}
        {required && <span aria-hidden="true"> *</span>}
      </span>
      {description && <span className={styles.description}>{description}</span>}
      {children}
      {error && (
        <span className={styles.error} role="alert">
          {error}
        </span>
      )}
    </label>
  );
}
