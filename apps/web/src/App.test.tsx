import { render, screen } from "@testing-library/react";

import { App } from "./App";
import { useAuthStore } from "./store/auth";

beforeEach(() => {
  useAuthStore.getState().clear();
  window.history.pushState({}, "", "/");
});

test("redirects to login when unauthenticated", () => {
  render(<App />);
  expect(screen.getByRole("button", { name: "Log in" })).toBeInTheDocument();
});

test("renders the shell and home when authenticated", () => {
  useAuthStore.getState().setToken("tok");
  render(<App />);
  expect(screen.getByText("Agents")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Home" })).toBeInTheDocument();
});
