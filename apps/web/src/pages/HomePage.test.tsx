import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { ApiError } from "../api/errors";
import { ThemeProvider } from "../design-system/theme/ThemeProvider";
import { HomePage } from "./HomePage";

const state = vi.hoisted(() => ({
  projectsError: null as Error | null,
  setupLoading: false,
}));

vi.mock("../api/queries", () => ({
  useProjects: () => ({
    data: state.projectsError
      ? undefined
      : [
          {
            id: "p1",
            name: "Demo",
            path: ".",
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
  useAgents: () =>
    state.setupLoading ? { data: undefined } : { data: [{ name: "Reviewer" }] },
  useProviders: () =>
    state.setupLoading ? { data: undefined } : { data: [{ id: "p1" }] },
  useModels: () =>
    state.setupLoading ? { data: undefined } : { data: [{ id: "m1" }] },
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
  state.setupLoading = false;
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
  expect(screen.getByText("Release plan")).toBeInTheDocument();
  expect(screen.getAllByText("Untitled session")).toHaveLength(2);
  expect(screen.getByText("Project root")).toBeInTheDocument();
  expect(screen.getByText("setup complete")).toBeInTheDocument();
  expect(screen.queryByText("Provider connected")).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /new project/i }),
  ).toBeInTheDocument();
});

test("does not auto-open onboarding before setup data loads", () => {
  state.setupLoading = true;
  render(
    <ThemeProvider forceScheme="dark">
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </ThemeProvider>,
  );
  expect(
    screen.queryByRole("dialog", { name: "Set up Agentbox" }),
  ).not.toBeInTheDocument();
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



