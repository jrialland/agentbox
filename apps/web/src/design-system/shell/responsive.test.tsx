import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { useAuthStore } from "../../store/auth";
import { ThemeProvider } from "../theme/ThemeProvider";
import { CommandShell } from "./CommandShell";

vi.mock("@mantine/hooks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@mantine/hooks")>();
  return { ...actual, useMediaQuery: () => true };
});

vi.mock("../navigation/ProjectPanel", () => ({
  ProjectPanel: () => <div>projects</div>,
}));

describe("CommandShell responsive", () => {
  it("renders mobile navigation and opens the project sheet", async () => {
    useAuthStore.setState({
      token: "t",
      user: { id: "1", username: "admin", permissions: [] },
    });
    render(
      <ThemeProvider forceScheme="dark">
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route element={<CommandShell />}>
              <Route index element={<div>workspace</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </ThemeProvider>,
    );
    expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Projects" }));
    expect(await screen.findByText("projects")).toBeInTheDocument();
  });
});
