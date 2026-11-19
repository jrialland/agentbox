import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("../api/queries", () => ({
  usePermissions: () => ({ data: [{ id: "p1", name: "agents:read", description: "d" }] }),
  useCreatePermission: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdatePermission: () => ({ mutateAsync: vi.fn() }),
  useDeletePermission: () => ({ mutateAsync: vi.fn() }),
  useRoles: () => ({ data: [{ id: "r1", name: "viewer", description: "v" }] }),
  useCreateRole: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateRole: () => ({ mutateAsync: vi.fn() }),
  useDeleteRole: () => ({ mutateAsync: vi.fn() }),
  useRolePermissions: () => ({ data: [] }),
  useSetRolePermissions: () => ({ mutateAsync: vi.fn() }),
  useUsers: () => ({ data: [] }),
  useCreateUser: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateUser: () => ({ mutateAsync: vi.fn() }),
  useDeleteUser: () => ({ mutateAsync: vi.fn() }),
  useUserRoles: () => ({ data: [] }),
  useSetUserRoles: () => ({ mutateAsync: vi.fn() }),
}));

import { AdminPage } from "./AdminPage";

function renderPage() {
  render(
    <MantineProvider>
      <AdminPage />
    </MantineProvider>,
  );
}

test("renders permissions tab", () => {
  renderPage();
  expect(screen.getByRole("tab", { name: "Permissions" })).toBeInTheDocument();
  expect(screen.getByText("agents:read")).toBeInTheDocument();
});

test("renders roles tab", () => {
  renderPage();
  fireEvent.click(screen.getByRole("tab", { name: "Roles" }));
  expect(screen.getByText("viewer")).toBeInTheDocument();
});
