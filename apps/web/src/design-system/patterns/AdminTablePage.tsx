import type { ReactNode } from "react";

import { ListPage } from "./ListPage";

export function AdminTablePage({
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
    <ListPage
      title={title}
      subtitle={subtitle}
      actions={actions}
      toolbar={toolbar}
    >
      {children}
    </ListPage>
  );
}
