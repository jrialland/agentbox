import { RiArrowLeftLine } from "@remixicon/react";
import { useNavigate } from "react-router-dom";

import { Button } from "../design-system/primitives/Button";
import { PageHeader } from "../design-system/primitives/PageHeader";
import { Panel } from "../design-system/primitives/Panel";
import { PageContainer } from "../design-system/shell/PageContainer";

export function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <PageContainer>
      <PageHeader title="404 — Page not found" subtitle="That route does not exist." />
      <Panel>
        <Panel.Body>
          <div style={{ display: "grid", gap: 12, justifyItems: "start" }}>
            <p>The page you are looking for may have moved or no longer exists.</p>
            <Button
              leftSection={<RiArrowLeftLine size={16} />}
              onClick={() => navigate("/")}
            >
              Back to Home
            </Button>
          </div>
        </Panel.Body>
      </Panel>
    </PageContainer>
  );
}
