import { describe, expect, it } from "vitest";

import { deriveOnboardingProgress } from "./onboardingProgress";

it("reports the first incomplete step", () => {
  const progress = deriveOnboardingProgress({
    providers: 1,
    models: 1,
    agents: 0,
    sessions: 0,
  });
  expect(progress.items.find((item) => item.id === "provider")?.done).toBe(true);
  expect(progress.nextStep).toBe("agent");
  expect(progress.complete).toBe(false);
});

it("is complete with all resources", () => {
  const progress = deriveOnboardingProgress({
    providers: 1,
    models: 1,
    agents: 1,
    sessions: 1,
  });
  expect(progress.complete).toBe(true);
  expect(progress.nextStep).toBe("done");
});
