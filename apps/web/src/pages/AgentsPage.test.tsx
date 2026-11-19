import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("../api/queries", () => ({
  useAgents: () => ({ data: [{ name: "bot", description: "d" }] }),
  useModels: () => ({ data: [] }),
  useCreateAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteAgent: () => ({ mutate: vi.fn() }),
  useUploadAvatar: () => ({ mutateAsync: vi.fn() }),
  useResetAvatar: () => ({ mutateAsync: vi.fn() }),
}));

import { AgentsPage } from "./AgentsPage";

test("renders an avatar for each agent", () => {
  render(
    <MantineProvider>
      <AgentsPage />
    </MantineProvider>,
  );
  expect(screen.getByRole("img", { name: "bot" })).toBeInTheDocument();
});
