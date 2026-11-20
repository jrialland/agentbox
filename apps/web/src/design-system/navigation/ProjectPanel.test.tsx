import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

import * as endpoints from "../../api/endpoints";
import { ThemeProvider } from "../theme/ThemeProvider";
import { ProjectPanel } from "./ProjectPanel";

vi.mock("@mantine/modals", () => ({
  modals: {
    openConfirmModal: (opts: { onConfirm?: () => void }) =>
      opts.onConfirm?.(),
  },
}));

const deleteSessionMock = vi.hoisted(() =>
  vi.fn().mockResolvedValue(undefined),
);
vi.mock("../../api/queries", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/queries")>();
  return {
    ...actual,
    useDeleteSession: () => ({ mutateAsync: deleteSessionMock }),
  };
});

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <ThemeProvider forceScheme="dark">
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route path="/" element={<ProjectPanel />} />
            <Route path="/sessions/:id" element={<div>Session page</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  vi.spyOn(endpoints, "fetchProjects").mockResolvedValue([
    {
      id: "p1",
      name: "Proj A",
      path: "/a",
      owner_id: "u1",
      created_at: "t1",
      extra_roots: [],
    },
  ] as never);
  vi.spyOn(endpoints, "fetchSessions").mockResolvedValue([
    { id: "s1", project_id: "p1", agent_id: "ag", created_at: "t2" },
  ] as never);
  vi.spyOn(endpoints, "fetchAgents").mockResolvedValue([
    { name: "coder" },
  ] as never);
});

test("renders projects with grouped sessions and navigates", async () => {
  renderPanel();
  expect(await screen.findByText("Proj A")).toBeInTheDocument();
  const session = await screen.findByText("Session 1");
  fireEvent.click(session);
  await waitFor(() =>
    expect(screen.getByText("Session page")).toBeInTheDocument(),
  );
});

test("creates a project via the modal", async () => {
  const created = vi.spyOn(endpoints, "createProject").mockResolvedValue({
    id: "p2",
    name: "New",
    path: "/n",
    owner_id: "u1",
    created_at: "t",
    extra_roots: [],
  } as never);
  renderPanel();
  fireEvent.click(
    await screen.findByRole("button", { name: /new project/i }),
  );
  fireEvent.change(await screen.findByLabelText("Name"), {
    target: { value: "New" },
  });
  fireEvent.change(screen.getByLabelText("Path"), {
    target: { value: "/n" },
  });
  fireEvent.change(screen.getByLabelText("Additional allowed folders"), {
    target: { value: "/extra" },
  });
  fireEvent.click(screen.getByRole("button", { name: /create/i }));
  await waitFor(() =>
    expect(created).toHaveBeenCalledWith(
      { name: "New", path: "/n", extra_roots: ["/extra"] },
      expect.anything(),
    ),
  );
});

test("edits project settings", async () => {
  const updated = vi.spyOn(endpoints, "updateProject").mockResolvedValue({
    id: "p1",
    name: "Proj A",
    path: "/a",
    owner_id: "u1",
    created_at: "t1",
    extra_roots: ["/extra"],
  } as never);
  renderPanel();
  fireEvent.click(
    await screen.findByLabelText("Project settings Proj A"),
  );
  fireEvent.change(
    await screen.findByLabelText("Additional allowed folders"),
    { target: { value: "/extra" } },
  );
  fireEvent.click(screen.getByRole("button", { name: /save/i }));
  await waitFor(() =>
    expect(updated).toHaveBeenCalledWith("p1", {
      name: "Proj A",
      extra_roots: ["/extra"],
    }),
  );
});

test("deletes a session", async () => {
  renderPanel();
  fireEvent.click(await screen.findByLabelText("Delete session s1"));
  await waitFor(() => expect(deleteSessionMock).toHaveBeenCalledWith("s1"));
});
