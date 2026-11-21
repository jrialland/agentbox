import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatSplit } from "./ChatSplit";

function renderSplit(appOpen = true) {
  return render(
    <MantineProvider>
      <ChatSplit
        appOpen={appOpen}
        chat={<div>chat pane</div>}
        app={<div>app pane</div>}
      />
    </MantineProvider>,
  );
}

describe("ChatSplit", () => {
  it("renders both panes and resizes with the divider", () => {
    renderSplit();
    expect(screen.getByText("chat pane")).toBeTruthy();
    expect(screen.getByText("app pane")).toBeTruthy();

    const separator = screen.getByRole("separator", { name: "Resize app panel" });
    const container = separator.parentElement as HTMLElement;
    vi.spyOn(container, "getBoundingClientRect").mockReturnValue({
      left: 0,
      width: 1000,
      top: 0,
      height: 600,
      right: 1000,
      bottom: 600,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });

    fireEvent.pointerDown(separator);
    fireEvent.pointerMove(window, { clientX: 600 });
    fireEvent.pointerUp(window);

    expect(separator.getAttribute("aria-valuenow")).toBe("60");
  });

  it("does not render the app pane when closed", () => {
    renderSplit(false);
    expect(screen.getByText("chat pane")).toBeTruthy();
    expect(screen.queryByText("app pane")).toBeNull();
  });

  it("opens and closes the app sheet on mobile", async () => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: query.includes("max-width: 960px"),
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;

    try {
      renderSplit();
      expect(await screen.findByText("App panel")).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: "Close app panel" }));
      await waitFor(() => expect(screen.queryByText("App panel")).toBeNull());
      expect(screen.getByRole("button", { name: "Open app" })).toBeTruthy();
    } finally {
      window.matchMedia = original;
    }
  });
});
