import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { ThemeProvider } from "../theme/ThemeProvider";
import { ErrorState } from "./ErrorState";

test("shows the message and invokes retry", () => {
  const retry = vi.fn();
  render(
    <ThemeProvider forceScheme="dark">
      <ErrorState title="Could not load providers" message="Server exploded" onRetry={retry} />
    </ThemeProvider>,
  );
  expect(screen.getByText("Server exploded")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(retry).toHaveBeenCalled();
});
