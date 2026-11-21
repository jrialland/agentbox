import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, vi } from "vitest";

const queries = vi.hoisted(() => {
  const state = {
    rolePermissionsError: null as Error | null,
    userRolesError: null as Error | null,
    rolePermissionsRefetch: vi.fn(),
    userRolesRefetch: vi.fn(),
    setRolePermissions: vi.fn(),
    setUserRoles: vi.fn(),
  };
  return {
    state,
    usePermissions: () => ({
      data: [{ id: "p1", name: "agents:read", description: "d" }],
    }),
    useCreatePermission: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useUpdatePermission: () => ({ mutateAsync: vi.fn() }),
    useDeletePermission: () => ({ mutateAsync: vi.fn() }),
    useRoles: () => ({
      data: [{ id: "r1", name: "viewer", description: "v" }],
    }),
    useCreateRole: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useUpdateRole: () => ({ mutateAsync: vi.fn() }),
    useDeleteRole: () => ({ mutateAsync: vi.fn() }),
    useRolePermissions: () => ({
      data: undefined,
      error: state.rolePermissionsError,
      refetch: state.rolePermissionsRefetch,
    }),
    useSetRolePermissions: () => ({ mutateAsync: state.setRolePermissions }),
    useUsers: () => ({
      data: [{ id: "u1", username: "bob", email: "b@x", is_active: true }],
    }),
    useCreateUser: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useUpdateUser: () => ({ mutateAsync: vi.fn() }),
    useDeleteUser: () => ({ mutateAsync: vi.fn() }),
    useUserRoles: () => ({
      data: undefined,
      error: state.userRolesError,
      refetch: state.userRolesRefetch,
    }),
    useSetUserRoles: () => ({ mutateAsync: state.setUserRoles }),
  };
});

vi.mock("../api/queries", () => queries);

import { AdminPage } from "./AdminPage";

function renderPage() {
  render(
    <MantineProvider>
      <AdminPage />
    </MantineProvider>,
  );
}

beforeEach(() => {
  queries.state.rolePermissionsError = null;
  queries.state.userRolesError = null;
  queries.state.rolePermissionsRefetch.mockReset();
  queries.state.userRolesRefetch.mockReset();
  queries.state.setRolePermissions.mockReset();
  queries.state.setUserRoles.mockReset();
});

test("shows an error instead of an empty role-permissions editor", () => {
  queries.state.rolePermissionsError = new Error("boom");

  renderPage();
  fireEvent.click(screen.getByRole("tab", { name: "Roles" }));
  fireEvent.click(screen.getByRole("button", { name: "Permissions" }));

  expect(
    screen.getByText("Could not load role permissions"),
  ).toBeInTheDocument();
  expect(screen.getByText("boom")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Save" }),
  ).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Retry" }));

  expect(queries.state.rolePermissionsRefetch).toHaveBeenCalled();
  expect(queries.state.setRolePermissions).not.toHaveBeenCalled();
});

test("shows an error instead of an empty user-roles editor", () => {
  queries.state.userRolesError = new Error("boom");

  renderPage();
  fireEvent.click(screen.getByRole("tab", { name: "Users" }));
  fireEvent.click(screen.getByRole("button", { name: "Roles" }));

  expect(screen.getByText("Could not load user roles")).toBeInTheDocument();
  expect(screen.getByText("boom")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Save" }),
  ).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Retry" }));

  expect(queries.state.userRolesRefetch).toHaveBeenCalled();
  expect(queries.state.setUserRoles).not.toHaveBeenCalled();
});
