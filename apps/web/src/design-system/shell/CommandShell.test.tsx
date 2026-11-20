import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { useAuthStore } from "../../store/auth";
import { ThemeProvider } from "../theme/ThemeProvider";
import { CommandShell } from "./CommandShell";

vi.mock("../navigation/ProjectPanel", () => ({
  ProjectPanel: () => <div>projects</div>,
}));

describe("CommandShell", () => {
  it("renders primary navigation and the outlet", () => {
    useAuthStore.setState({
      token: "t",
      user: {
        id: "1",
        username: "admin",
        permissions: ["agents:create", "api_keys:manage"],
      },
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
    expect(
      screen.getByRole("navigation", { name: "Primary navigation" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Agents" })).toBeInTheDocument();
    expect(screen.getByText("workspace")).toBeInTheDocument();
  });
});
