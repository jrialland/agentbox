import type { ReactNode } from "react";

import styles from "./forms.module.css";

export function FormField({
  label,
  description,
  error,
  required,
  htmlFor,
  help,
  children,
}: {
  label: string;
  description?: string;
  error?: string | null;
  required?: boolean;
  htmlFor?: string;
  help?: ReactNode;
  children: ReactNode;
}) {
  const content = (
    <>
      <span className={styles.labelRow}>
        <span className={styles.label}>
          {label}
          {required && <span aria-hidden="true"> *</span>}
        </span>
        {help}
      </span>
      {description && <span className={styles.description}>{description}</span>}
      {children}
      {error && (
        <span className={styles.error} role="alert">
          {error}
        </span>
      )}
    </>
  );

  if (htmlFor) {
    return (
      <div className={styles.field}>
        <span className={styles.labelRow}>
          <label className={styles.label} htmlFor={htmlFor}>
            {label}
            {required && <span aria-hidden="true"> *</span>}
          </label>
          {help}
        </span>
        {description && (
          <span className={styles.description}>{description}</span>
        )}
        {children}
        {error && (
          <span className={styles.error} role="alert">
            {error}
          </span>
        )}
      </div>
    );
  }

  return <label className={styles.field}>{content}</label>;
}

