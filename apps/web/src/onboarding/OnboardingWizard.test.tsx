import { fireEvent, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";

vi.mock("../api/queries", () => ({
  useModels: () => ({ data: [{ id: "m1", name: "model-a", provider_id: "p1" }] }),
  useProviders: () => ({ data: [{ id: "p1", name: "provider-a", kind: "generic" }] }),
  useAgents: () => ({ data: [] }),
  useTestProvider: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCreateProvider: () => ({ mutateAsync: vi.fn(async () => ({ id: "p1" })), isPending: false }),
  useRefreshModels: () => ({ mutateAsync: vi.fn(async () => []), isPending: false }),
  useCreateAgent: () => ({ mutateAsync: vi.fn(async () => ({ name: "agent-a" })), isPending: false }),
  useCreateProject: () => ({ mutateAsync: vi.fn(async () => ({ id: "prj1" })), isPending: false }),
  useCreateSession: () => ({ mutateAsync: vi.fn(async () => ({ id: "s1" })), isPending: false }),
}));

import { renderWithTheme } from "../test/render";
import { OnboardingWizard } from "./OnboardingWizard";

test("moves from welcome to provider setup and can be skipped", async () => {
  const onClose = vi.fn();
  renderWithTheme(
    <QueryClientProvider client={new QueryClient()}>
      <OnboardingWizard opened initialStep="welcome" onClose={onClose} onDone={() => {}} />
    </QueryClientProvider>,
  );
  expect(screen.getByText("Connect your first provider")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Skip setup" }));
  expect(onClose).toHaveBeenCalled();
});
