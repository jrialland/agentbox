import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("../api/queries", () => ({
  useProviders: () => ({ data: [{ id: "p1", name: "prov", kind: "generic" }] }),
  useModels: () => ({ data: [{ id: "m1", provider_id: "p1", name: "m" }] }),
  useCreateProvider: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteProvider: () => ({ mutateAsync: vi.fn() }),
  useRefreshModels: () => ({ mutateAsync: vi.fn() }),
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
