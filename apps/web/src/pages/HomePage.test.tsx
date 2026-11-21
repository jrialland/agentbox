import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { ApiError } from "../api/errors";
import { ThemeProvider } from "../design-system/theme/ThemeProvider";
import { HomePage } from "./HomePage";

const state = vi.hoisted(() => ({ projectsError: null as Error | null }));

vi.mock("../api/queries", () => ({
  useProjects: () => ({
    data: state.projectsError
      ? undefined
      : [
          {
            id: "p1",
            name: "Demo",
            path: "/demo",
            owner_id: "u1",
            created_at: "t1",
            extra_roots: [],
          },
        ],
    error: state.projectsError,
    refetch: vi.fn(),
  }),
  useSessions: () => ({
    data: [
      {
        id: "s1",
        project_id: "p1",
        agent_id: "Reviewer",
        created_at: "t2",
      },
      {
        id: "s2",
        project_id: "p1",
        agent_id: "Reviewer",
        title: "Release plan",
        created_at: "t3",
      },
      {
        id: "s3",
        project_id: "p1",
        agent_id: "Whitespace",
        title: "   ",
        created_at: "t4",
      },
    ],
  }),
  useAgents: () => ({ data: [{ name: "Reviewer" }] }),
  useProviders: () => ({ data: [{ id: "p1" }] }),
  useModels: () => ({ data: [{ id: "m1" }] }),
  useCreateProject: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCreateProvider: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRefreshModels: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCreateAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCreateSession: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useTestProvider: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateProject: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

beforeEach(() => {
  state.projectsError = null;
});

test("renders the command center dashboard", () => {
  render(
    <ThemeProvider forceScheme="dark">
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </ThemeProvider>,
  );
  expect(screen.getByRole("heading", { name: "Home" })).toBeInTheDocument();
  expect(screen.getAllByText("Demo").length).toBeGreaterThan(0);
  expect(screen.getByText("Reviewer")).toBeInTheDocument();
  expect(screen.getByText("Release plan")).toBeInTheDocument();
  expect(screen.getByText("Whitespace")).toBeInTheDocument();
  expect(screen.getByText("Provider connected")).toBeInTheDocument();
  expect(screen.getByText("Agent ready")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /new project/i }),
  ).toBeInTheDocument();
});

test("shows an error state instead of an empty project list", () => {
  state.projectsError = new ApiError("boom", 500);
  render(
    <ThemeProvider forceScheme="dark">
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </ThemeProvider>,
  );
  expect(screen.getByText("Could not load projects")).toBeInTheDocument();
  expect(screen.queryByText("No projects")).not.toBeInTheDocument();
});



