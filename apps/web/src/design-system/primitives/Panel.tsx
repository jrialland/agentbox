import type { ReactNode } from "react";

import styles from "./primitives.module.css";

function PanelRoot({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`${styles.panel} ${className ?? ""}`}>{children}</section>
  );
}

function PanelHeader({ children }: { children: ReactNode }) {
  return <header className={styles.panelHeader}>{children}</header>;
}

function PanelBody({ children }: { children: ReactNode }) {
  return <div className={styles.panelBody}>{children}</div>;
}

export const Panel = Object.assign(PanelRoot, {
  Header: PanelHeader,
  Body: PanelBody,
});
