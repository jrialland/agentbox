import type { RemixiconComponentType } from "@remixicon/react";
import type { ReactNode } from "react";

import { EmptyState } from "../primitives/EmptyState";
import { Panel } from "../primitives/Panel";

export function EmptyStatePanel({
  icon,
  title,
  description,
  action,
}: {
  icon: RemixiconComponentType;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <Panel>
      <Panel.Body>
        <EmptyState
          icon={icon}
          title={title}
          description={description}
          action={action}
        />
      </Panel.Body>
    </Panel>
  );
}
