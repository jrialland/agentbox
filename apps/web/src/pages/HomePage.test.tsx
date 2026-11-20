import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { ThemeProvider } from "../design-system/theme/ThemeProvider";
import { HomePage } from "./HomePage";

vi.mock("../api/queries", () => ({
  useProjects: () => ({
    data: [
      {
        id: "p1",
        name: "Demo",
        path: "/demo",
        owner_id: "u1",
        created_at: "t1",
        extra_roots: [],
      },
    ],
  }),
  useSessions: () => ({
    data: [
      {
        id: "s1",
        project_id: "p1",
        agent_id: "Reviewer",
        created_at: "t2",
      },
    ],
  }),
  useAgents: () => ({ data: [{ name: "Reviewer" }] }),
  useCreateProject: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateProject: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

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
  expect(
    screen.getByRole("button", { name: /new project/i }),
  ).toBeInTheDocument();
});

