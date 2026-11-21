import { RiErrorWarningLine } from "@remixicon/react";

import { Button } from "../primitives/Button";
import { EmptyState } from "../primitives/EmptyState";
import { Panel } from "../primitives/Panel";

export function ErrorState({
  title = "Could not load data",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry: () => void;
}) {
  return (
    <Panel>
      <Panel.Body>
        <EmptyState
          icon={RiErrorWarningLine}
          title={title}
          description={message}
          action={<Button onClick={onRetry}>Retry</Button>}
        />
      </Panel.Body>
    </Panel>
  );
}
