import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithTheme as render } from "../test/render";
import { ErrorCard } from "./ErrorCard";
import { MessageTurn } from "./MessageTurn";
import { RunStatus } from "./RunStatus";

describe("ErrorCard", () => {
  it("shows error details and calls retry", () => {
    const onRetry = vi.fn();
    render(
      <ErrorCard
        error={{ code: "context_window", message: "Context window exceeded" }}
        onRetry={onRetry}
      />,
    );

    expect(screen.getByText("Context window exceeded")).toBeTruthy();
    expect(screen.getByText("context_window")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("shows a friendly provider auth message with raw details", () => {
    render(
      <ErrorCard
        error={{
          message:
            "status_code: 401, body: {'message': 'Authentication Fails, Your api key is invalid'}",
        }}
        onRetry={() => {}}
      />,
    );

    expect(
      screen.getByText(
        "Provider authentication failed. Check the API key in Providers.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Details")).toBeTruthy();
  });
});

describe("RunStatus", () => {
  it("shows elapsed time and calls stop", () => {
    const onStop = vi.fn();
    render(<RunStatus running elapsedMs={2300} onStop={onStop} />);

    expect(screen.getByText("Thinking.")).toBeTruthy();
    expect(screen.getByText("2.3s")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(onStop).toHaveBeenCalled();
  });

  it("renders nothing when idle", () => {
    render(<RunStatus running={false} elapsedMs={0} onStop={() => {}} />);
    expect(screen.queryByText("Thinking.")).toBeNull();
  });
});

describe("MessageTurn retry", () => {
  it("offers retry for cancelled turns", () => {
    const onRetry = vi.fn();
    render(
      <MessageTurn
        sessionId="s1"
        agentName="Coder"
        onRetry={onRetry}
        message={{
          id: "m3",
          role: "assistant",
          content: "partial",
          activity: { status: "cancelled" },
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledWith("m3");
  });

  it("renders a per-turn error card", () => {
    render(
      <MessageTurn
        sessionId="s1"
        agentName="Coder"
        onRetry={() => {}}
        message={{
          id: "m4",
          role: "assistant",
          content: "",
          activity: {
            status: "error",
            error: { code: 500, message: "Provider unavailable" },
          },
        }}
      />,
    );

    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("Provider unavailable")).toBeTruthy();
  });
});

