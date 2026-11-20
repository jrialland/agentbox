import type { ReactNode } from "react";

import { PageHeader } from "../primitives/PageHeader";

export function ListPage({
  title,
  subtitle,
  actions,
  toolbar,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  toolbar?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div>
      <PageHeader title={title} subtitle={subtitle} actions={actions} />
      {toolbar}
      {children}
    </div>
  );
}
