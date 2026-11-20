import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ThemeProvider } from "./ThemeProvider";

describe("ThemeProvider", () => {
  it("renders children and sets a data-theme attribute", () => {
    render(
      <ThemeProvider forceScheme="dark">
        <span>hello</span>
      </ThemeProvider>,
    );
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
