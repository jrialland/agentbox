import { render, screen } from "@testing-library/react";

import { App } from "./App";

test("renders the shell navigation", () => {
  render(<App />);
  expect(screen.getByText("Agents")).toBeInTheDocument();
  expect(screen.getByText("Projects")).toBeInTheDocument();
});

test("renders the home page", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "Home" })).toBeInTheDocument();
});
