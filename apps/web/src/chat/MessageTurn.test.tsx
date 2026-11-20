import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ActivityChips } from "./ActivityChips";
import { MessageTurn } from "./MessageTurn";

describe("MessageTurn", () => {
  it("renders user attachment chips with authenticated download links", () => {
    render(
      <MessageTurn
        sessionId="s1"
        agentName="Coder"
        message={{
          id: "m1",
          role: "user",
          content: "See attached",
          attachments: [
            { id: "a1", filename: "notes.txt", media_type: "text/plain" },
          ],
        }}
      />,
    );

    expect(screen.getByText("See attached")).toBeTruthy();
    const link = screen.getByRole("link", { name: /notes\.txt/ });
    expect(link.getAttribute("href")).toContain("/sessions/s1/attachments/a1");
    expect(screen.getByText("text/plain")).toBeTruthy();
  });

  it("renders assistant markdown, activity and cancelled state", () => {
    render(
      <MessageTurn
        sessionId="s1"
        agentName="Coder"
        message={{
          id: "m2",
          role: "assistant",
          content: "# Partial answer",
          activity: {
            status: "cancelled",
            reasoning_ms: 1200,
            tools: [{ name: "read", status: "success", duration_ms: 420 }],
          },
        }}
      />,
    );

    expect(screen.getByRole("heading", { name: "Partial answer" })).toBeTruthy();
    expect(screen.getByText("cancelled")).toBeTruthy();
    expect(screen.getByText("Reasoning 1.2s")).toBeTruthy();
  });
});

describe("ActivityChips", () => {
  it("shows compact counts and expands to tool details", () => {
    render(
      <ActivityChips
        activity={{
          reasoning_ms: 1200,
          tools: [
            { name: "read", status: "success", duration_ms: 420 },
            { name: "grep", status: "error", duration_ms: 80 },
          ],
        }}
      />,
    );

    expect(screen.getByText("Reasoning 1.2s")).toBeTruthy();
    expect(screen.getByText("2 tools")).toBeTruthy();
    const summary = screen.getByText("Activity").closest("summary");
    expect(summary).toBeTruthy();
    fireEvent.click(summary as HTMLElement);

    expect(screen.getByText("read")).toBeTruthy();
    expect(screen.getByText("success")).toBeTruthy();
    expect(screen.getByText("420ms")).toBeTruthy();
    expect(screen.getByText("grep")).toBeTruthy();
    expect(screen.getByText("error")).toBeTruthy();
  });
});
