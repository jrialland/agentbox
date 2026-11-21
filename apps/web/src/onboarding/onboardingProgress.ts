export type OnboardingStep = "welcome" | "provider" | "agent" | "session" | "done";

export type OnboardingSnapshot = {
  providers: number;
  models: number;
  agents: number;
  sessions: number;
};

export type OnboardingProgress = {
  items: { id: "provider" | "model" | "agent" | "session"; label: string; done: boolean }[];
  nextStep: OnboardingStep;
  complete: boolean;
};

export function deriveOnboardingProgress(
  snapshot: OnboardingSnapshot,
): OnboardingProgress {
  const items = [
    { id: "provider" as const, label: "Provider connected", done: snapshot.providers > 0 },
    { id: "model" as const, label: "Model available", done: snapshot.models > 0 },
    { id: "agent" as const, label: "Agent ready", done: snapshot.agents > 0 },
    { id: "session" as const, label: "First session started", done: snapshot.sessions > 0 },
  ];
  const next = items.find((item) => !item.done);
  const map = {
    provider: "provider",
    model: "provider",
    agent: "agent",
    session: "session",
  } as const;
  return {
    items,
    nextStep: next ? map[next.id] : "done",
    complete: !next,
  };
}
