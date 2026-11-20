import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { App } from "./App";
import * as endpoints from "./api/endpoints";
import { useAuthStore } from "./store/auth";

beforeEach(() => {
  useAuthStore.getState().clear();
  window.history.pushState({}, "", "/");
  vi.spyOn(endpoints, "fetchProjects").mockResolvedValue([]);
  vi.spyOn(endpoints, "fetchSessions").mockResolvedValue([]);
  vi.spyOn(endpoints, "fetchAgents").mockResolvedValue([]);
});

test("redirects to login when unauthenticated", () => {
  render(<App />);
  expect(screen.getByRole("button", { name: "Log in" })).toBeInTheDocument();
});

test("renders the shell and home when authenticated", () => {
  useAuthStore.getState().setToken("tok");
  render(<App />);
  expect(screen.getByRole("link", { name: "Agents" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Home" })).toBeInTheDocument();
});

