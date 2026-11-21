import type { Meta, StoryObj } from "@storybook/react-vite";

import { HomeChecklist } from "./HomeChecklist";
import { deriveOnboardingProgress } from "./onboardingProgress";

const meta: Meta = { title: "Onboarding/States" };
export default meta;

export const Checklist: StoryObj = {
  render: () => (
    <HomeChecklist
      progress={deriveOnboardingProgress({
        providers: 1,
        models: 1,
        agents: 0,
        sessions: 0,
      })}
      onOpenStep={() => {}}
    />
  ),
};

export const Welcome: StoryObj = {
  render: () => (
    <div style={{ display: "grid", gap: 12, maxWidth: 560 }}>
      <h2>Connect your first provider</h2>
      <p>
        Agentbox needs one model endpoint before it can create an agent and start
        a session.
      </p>
      <button type="button">Get started</button>
    </div>
  ),
};
