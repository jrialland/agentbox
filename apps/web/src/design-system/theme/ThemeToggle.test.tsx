import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { ThemeProvider } from "./ThemeProvider";
import { ThemeToggle } from "./ThemeToggle";

describe("ThemeToggle", () => {
  beforeEach(() => {
    localStorage.setItem("agentbox-color-scheme", "dark");
  });

  it("switches from dark to light", async () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>,
    );
    await waitFor(() =>
      expect(document.documentElement.dataset.theme).toBe("dark"),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /switch to light theme/i }),
    );
    await waitFor(() =>
      expect(document.documentElement.dataset.theme).toBe("light"),
    );
  });
});
