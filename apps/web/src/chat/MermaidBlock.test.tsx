import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithTheme as render } from "../test/render";

const mermaidMock = vi.hoisted(() => ({
  parse: vi.fn(async () => true),
  render: vi.fn(async (id: string) => {
    const element = document.createElement("div");
    element.id = id;
    document.body.append(element);
    return { svg: '<svg data-testid="diagram"></svg>' };
  }),
}));

vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    parse: mermaidMock.parse,
    render: mermaidMock.render,
  },
}));

import { MermaidBlock } from "./MermaidBlock";

describe("MermaidBlock", () => {
  beforeEach(() => {
    mermaidMock.parse.mockReset();
    mermaidMock.parse.mockResolvedValue(true);
    mermaidMock.render.mockClear();
  });

  it("does not render an incomplete fence", () => {
    render(<MermaidBlock source="graph TD; A-->B" complete={false} />);
    expect(screen.getByRole("status").textContent).toContain("Diagram building");
    expect(mermaidMock.parse).not.toHaveBeenCalled();
    expect(mermaidMock.render).not.toHaveBeenCalled();
  });

  it("renders a complete valid diagram", async () => {
    render(<MermaidBlock source="graph TD; A-->B" complete />);
    await waitFor(() => expect(screen.getByTestId("diagram")).toBeTruthy());
    expect(mermaidMock.parse).toHaveBeenCalledWith("graph TD; A-->B");
  });

  it("offers zoom and copy controls for a rendered diagram", async () => {
    render(<MermaidBlock source="graph TD; A-->B" complete />);
    await waitFor(() => expect(screen.getByTestId("diagram")).toBeTruthy());
    expect(screen.getByRole("button", { name: "Zoom in" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Zoom out" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reset zoom" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Copy diagram" })).toBeTruthy();
  });

  it("toggles fullscreen with the browser fullscreen API", async () => {
    const enabledDescriptor = Object.getOwnPropertyDescriptor(
      document,
      "fullscreenEnabled",
    );
    const elementDescriptor = Object.getOwnPropertyDescriptor(
      document,
      "fullscreenElement",
    );
    const originalRequest = HTMLElement.prototype.requestFullscreen;
    const originalExit = document.exitFullscreen;
    let current: Element | null = null;

    Object.defineProperty(document, "fullscreenEnabled", {
      configurable: true,
      value: true,
    });
    Object.defineProperty(document, "fullscreenElement", {
      configurable: true,
      get: () => current,
    });
    HTMLElement.prototype.requestFullscreen = vi.fn(async function (
      this: HTMLElement,
    ) {
      current = this;
      document.dispatchEvent(new Event("fullscreenchange"));
    });
    document.exitFullscreen = vi.fn(async () => {
      current = null;
      document.dispatchEvent(new Event("fullscreenchange"));
    });

    try {
      const { unmount } = render(
        <MermaidBlock source="graph TD; A-->B" complete />,
      );
      await waitFor(() => expect(screen.getByTestId("diagram")).toBeTruthy());

      fireEvent.click(
        screen.getByRole("button", { name: "Enter fullscreen" }),
      );
      await waitFor(() =>
        expect(
          screen.getByRole("button", { name: "Exit fullscreen" }),
        ).toBeTruthy(),
      );

      fireEvent.click(
        screen.getByRole("button", { name: "Exit fullscreen" }),
      );
      await waitFor(() =>
        expect(
          screen.getByRole("button", { name: "Enter fullscreen" }),
        ).toBeTruthy(),
      );
      unmount();
    } finally {
      if (enabledDescriptor) {
        Object.defineProperty(
          document,
          "fullscreenEnabled",
          enabledDescriptor,
        );
      } else {
        Reflect.deleteProperty(document, "fullscreenEnabled");
      }
      if (elementDescriptor) {
        Object.defineProperty(
          document,
          "fullscreenElement",
          elementDescriptor,
        );
      } else {
        Reflect.deleteProperty(document, "fullscreenElement");
      }
      if (originalRequest) {
        HTMLElement.prototype.requestFullscreen = originalRequest;
      } else {
        Reflect.deleteProperty(HTMLElement.prototype, "requestFullscreen");
      }
      document.exitFullscreen = originalExit;
    }
  });

  it("shows a compact fallback and cleans up on failure", async () => {
    mermaidMock.parse.mockRejectedValueOnce(new Error("bad syntax"));
    render(<MermaidBlock source="not a diagram" complete />);
    await waitFor(() =>
      expect(screen.getByText("Diagram could not be rendered")).toBeTruthy(),
    );
    expect(screen.getByText("not a diagram")).toBeTruthy();
    expect(document.body.querySelector('[id^="mermaid-"]')).toBeNull();
  });

  it("resets failure when the source changes", async () => {
    mermaidMock.parse.mockRejectedValueOnce(new Error("bad syntax"));
    const { rerender } = render(<MermaidBlock source="bad" complete />);
    await waitFor(() =>
      expect(screen.getByText("Diagram could not be rendered")).toBeTruthy(),
    );

    rerender(<MermaidBlock source="graph TD; A-->B" complete />);
    await waitFor(() => expect(screen.getByTestId("diagram")).toBeTruthy());
    expect(screen.queryByText("Diagram could not be rendered")).toBeNull();
  });
});
