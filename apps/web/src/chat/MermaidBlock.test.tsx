import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
