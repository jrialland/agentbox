import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("../api/queries", () => ({
  usePermissions: () => ({ data: [{ id: "p1", name: "agents:read", description: "d" }] }),
  useCreatePermission: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdatePermission: () => ({ mutateAsync: vi.fn() }),
  useDeletePermission: () => ({ mutateAsync: vi.fn() }),
  useRoles: () => ({ data: [] }),
  useUsers: () => ({ data: [] }),
}));

import { AdminPage } from "./AdminPage";

test("renders tabs and permissions", () => {
  render(
    <MantineProvider>
      <AdminPage />
    </MantineProvider>,
  );
  expect(screen.getByRole("tab", { name: "Permissions" })).toBeInTheDocument();
  expect(screen.getByText("agents:read")).toBeInTheDocument();
});
