import type { RemixiconComponentType } from "@remixicon/react";
import type { ReactNode } from "react";

import { getHelpEntry } from "../../help/content";
import { HelpLink } from "../../help/HelpLink";
import type { HelpId } from "../../help/types";
import { EmptyStatePanel } from "./EmptyStatePanel";

export function GuidedEmptyState({
  icon,
  title,
  description,
  action,
  helpId,
}: {
  icon: RemixiconComponentType;
  title: string;
  description: string;
  action?: ReactNode;
  helpId: HelpId;
}) {
  return (
    <EmptyStatePanel
      icon={icon}
      title={title}
      description={description}
      action={
        <div style={{ display: "grid", gap: 8, justifyItems: "center" }}>
          {action}
          <HelpLink id={helpId}>Learn about {getHelpEntry(helpId).title}</HelpLink>
        </div>
      }
    />
  );
}
