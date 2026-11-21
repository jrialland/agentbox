import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

import * as endpoints from "../../api/endpoints";
import { ThemeProvider } from "../theme/ThemeProvider";
import { ProjectPanel } from "./ProjectPanel";

const deleteSessionMock = vi.hoisted(() =>
  vi.fn().mockResolvedValue(undefined),
);
const deleteProjectMock = vi.hoisted(() =>
  vi.fn().mockResolvedValue(undefined),
);
const renameSessionMock = vi.hoisted(() =>
  vi.fn().mockResolvedValue(undefined),
);
vi.mock("../../api/queries", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/queries")>();
  return {
    ...actual,
    useDeleteSession: () => ({ mutateAsync: deleteSessionMock }),
    useDeleteProject: () => ({ mutateAsync: deleteProjectMock }),
    useRenameSession: () => ({ mutateAsync: renameSessionMock }),
  };
});

function renderPanel(initialEntries: string[] = ["/"]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <ThemeProvider forceScheme="dark">
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={initialEntries}>
          <Routes>
            <Route
              path="/"
              element={
                <>
                  <ProjectPanel />
                  <div>Home page</div>
                </>
              }
            />
            <Route
              path="/agents"
              element={
                <>
                  <ProjectPanel />
                  <div>Agents page</div>
                </>
              }
            />
            <Route
              path="/sessions/:id"
              element={
                <>
                  <ProjectPanel />
                  <div>Session page</div>
                </>
              }
            />
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

test("shows and renames a session title", async () => {
  vi.spyOn(endpoints, "fetchSessions").mockResolvedValueOnce([
    {
      id: "s1",
      project_id: "p1",
      agent_id: "ag",
      title: "Release plan",
      created_at: "t2",
    },
  ] as never);
  renderPanel();
  expect(await screen.findByText("Release plan")).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("Rename session s1"));
  fireEvent.change(screen.getByLabelText("Session title"), {
    target: { value: "Launch checklist" },
  });
  fireEvent.keyDown(screen.getByLabelText("Session title"), { key: "Enter" });
  await waitFor(() =>
    expect(renameSessionMock).toHaveBeenCalledWith({
      sid: "s1",
      title: "Launch checklist",
    }),
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

test("blocks blank project names", async () => {
  const created = vi.spyOn(endpoints, "createProject");
  renderPanel();
  fireEvent.click(
    await screen.findByRole("button", { name: /new project/i }),
  );
  fireEvent.change(await screen.findByLabelText("Name"), {
    target: { value: "   " },
  });
  fireEvent.change(screen.getByLabelText("Path"), {
    target: { value: "/n" },
  });
  fireEvent.click(screen.getByRole("button", { name: /create/i }));
  expect(await screen.findByText("Name is required.")).toBeInTheDocument();
  expect(created).not.toHaveBeenCalled();
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

test("confirms before deleting a session", async () => {
  renderPanel();
  fireEvent.click(await screen.findByLabelText("Delete session s1"));
  fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
  await waitFor(() => expect(deleteSessionMock).toHaveBeenCalledWith("s1"));
});

test("requires the project name before deleting", async () => {
  renderPanel();
  fireEvent.click(await screen.findByLabelText("Delete Proj A"));
  const confirm = await screen.findByRole("button", { name: "Delete" });
  expect(confirm).toBeDisabled();
  fireEvent.change(screen.getByLabelText(/type Proj A/i), {
    target: { value: "Proj A" },
  });
  fireEvent.click(confirm);
  await waitFor(() => expect(deleteProjectMock).toHaveBeenCalledWith("p1"));
});

test("stays on a non-project route after deleting a project", async () => {
  renderPanel(["/agents"]);
  fireEvent.click(await screen.findByLabelText("Delete Proj A"));
  const confirm = await screen.findByRole("button", { name: "Delete" });
  fireEvent.change(screen.getByLabelText(/type Proj A/i), {
    target: { value: "Proj A" },
  });
  fireEvent.click(confirm);
  await waitFor(() => expect(deleteProjectMock).toHaveBeenCalledWith("p1"));
  expect(screen.getByText("Agents page")).toBeInTheDocument();
  expect(screen.queryByText("Home page")).not.toBeInTheDocument();
});

test("navigates home after deleting the project of the current session", async () => {
  renderPanel(["/sessions/s1"]);
  fireEvent.click(await screen.findByLabelText("Delete Proj A"));
  const confirm = await screen.findByRole("button", { name: "Delete" });
  fireEvent.change(screen.getByLabelText(/type Proj A/i), {
    target: { value: "Proj A" },
  });
  fireEvent.click(confirm);
  await waitFor(() =>
    expect(screen.getByText("Home page")).toBeInTheDocument(),
  );
});
