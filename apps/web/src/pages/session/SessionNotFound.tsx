import { RiArrowLeftLine, RiFolderLine } from "@remixicon/react";
import { useNavigate } from "react-router-dom";

import { Button } from "../../design-system/primitives/Button";
import { PageHeader } from "../../design-system/primitives/PageHeader";
import { Panel } from "../../design-system/primitives/Panel";
import { PageContainer } from "../../design-system/shell/PageContainer";

export function SessionNotFound() {
  const navigate = useNavigate();
  return (
    <PageContainer>
      <PageHeader
        title="Session not found"
        subtitle="This session may have been deleted or is unavailable."
      />
      <Panel>
        <Panel.Body>
          <div style={{ display: "grid", gap: 12, justifyItems: "start" }}>
            <p>
              The session you are looking for does not exist or you no longer have
              access to it.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              <Button
                leftSection={<RiArrowLeftLine size={16} />}
                onClick={() => navigate("/")}
              >
                Back to Home
              </Button>
              <Button
                variant="light"
                leftSection={<RiFolderLine size={16} />}
                onClick={() => navigate("/")}
              >
                Browse projects
              </Button>
            </div>
          </div>
        </Panel.Body>
      </Panel>
    </PageContainer>
  );
}
