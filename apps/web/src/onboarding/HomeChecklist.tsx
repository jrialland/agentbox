import { Badge } from "../design-system/primitives/Badge";
import { Button } from "../design-system/primitives/Button";
import { Panel } from "../design-system/primitives/Panel";
import { StatusChip } from "../design-system/primitives/StatusChip";
import type { OnboardingProgress, OnboardingStep } from "./onboardingProgress";

export function HomeChecklist({
  progress,
  onOpenStep,
}: {
  progress: OnboardingProgress;
  onOpenStep: (step: OnboardingStep) => void;
}) {
  const done = progress.items.filter((item) => item.done).length;
  return (
    <Panel>
      <Panel.Header>
        <span>Setup</span>
        <Badge tone={progress.complete ? "success" : "neutral"}>
          {done} of {progress.items.length} complete
        </Badge>
      </Panel.Header>
      <Panel.Body>
        {progress.complete ? (
          <StatusChip tone="success">setup complete</StatusChip>
        ) : (
          <>
            <ul
              style={{
                display: "grid",
                gap: 8,
                listStyle: "none",
                margin: 0,
                padding: 0,
              }}
            >
              {progress.items.map((item) => (
                <li
                  key={item.id}
                  style={{ alignItems: "center", display: "flex", gap: 8 }}
                >
                  <StatusChip tone={item.done ? "success" : "neutral"}>
                    {item.done ? "done" : "next"}
                  </StatusChip>
                  <span style={{ flex: 1 }}>{item.label}</span>
                </li>
              ))}
            </ul>
            <Button mt="sm" onClick={() => onOpenStep(progress.nextStep)}>
              Continue
            </Button>
          </>
        )}
      </Panel.Body>
    </Panel>
  );
}
