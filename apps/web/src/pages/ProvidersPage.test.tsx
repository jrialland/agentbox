import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("../api/queries", () => ({
  useProviders: () => ({ data: [{ id: "p1", name: "prov", kind: "generic" }] }),
  useModels: () => ({ data: [{ id: "m1", provider_id: "p1", name: "m" }] }),
  useCreateProvider: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteProvider: () => ({ mutateAsync: vi.fn() }),
  useRefreshModels: () => ({ mutateAsync: vi.fn() }),
  useTestProvider: () => ({
    mutateAsync: vi.fn(async () => ({
      ok: true,
      latency_ms: 25,
      model_count: 2,
      sample_models: ["a", "b"],
    })),
    isPending: false,
  }),
  useUpdateProvider: () => ({ mutateAsync: vi.fn() }),
  useCreateModel: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteModel: () => ({ mutateAsync: vi.fn() }),
}));

import { ProvidersPage } from "./ProvidersPage";

test("renders Providers and Models tabs", () => {
  render(
    <MantineProvider>
      <ProvidersPage />
    </MantineProvider>,
  );
  expect(screen.getByRole("tab", { name: "Providers" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Models" })).toBeInTheDocument();
});

test("shows configured, then verified after a successful test", async () => {
  render(
    <MantineProvider>
      <ProvidersPage />
    </MantineProvider>,
  );
  expect(screen.getByText("configured")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Test connection" }));
  await waitFor(() => expect(screen.getByText("verified")).toBeInTheDocument());
});
