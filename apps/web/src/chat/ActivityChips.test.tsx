import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ActivityChips } from "./ActivityChips";

describe("ActivityChips", () => {
  it("renders sub-millisecond tool durations as <1ms", () => {
    render(
      <ActivityChips
        defaultOpen
        activity={{
          reasoning_ms: 0,
          tools: [{ name: "list_directory", status: "success", duration_ms: 0 }],
        }}
      />,
    );

    expect(screen.getByText("<1ms")).toBeInTheDocument();
  });

  it("renders persisted reasoning text and tool input/output", () => {
    render(
      <ActivityChips
        defaultOpen
        activity={{
          reasoning_ms: 120,
          reasoning_text: "I should inspect the project root.",
          tools: [
            {
              name: "list_directory",
              status: "success",
              duration_ms: 4,
              args: '{"path":"."}',
              result: "AGENTS.md README.md",
            },
          ],
        }}
      />,
    );

    expect(
      screen.getByText("I should inspect the project root."),
    ).toBeInTheDocument();
    expect(screen.getByText('{"path":"."}')).toBeInTheDocument();
    expect(screen.getByText("AGENTS.md README.md")).toBeInTheDocument();
  });
});
