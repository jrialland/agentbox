import { fireEvent, screen } from "@testing-library/react";
import { vi } from "vitest";

import { renderWithTheme } from "../test/render";
import { HomeChecklist } from "./HomeChecklist";
import { deriveOnboardingProgress } from "./onboardingProgress";

test("opens the first incomplete step", () => {
  const progress = deriveOnboardingProgress({
    providers: 1,
    models: 1,
    agents: 0,
    sessions: 0,
  });
  const onOpenStep = vi.fn();
  renderWithTheme(<HomeChecklist progress={progress} onOpenStep={onOpenStep} />);
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  expect(onOpenStep).toHaveBeenCalledWith("agent");
});
