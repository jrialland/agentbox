import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithTheme } from "../test/render";
import { getHelpEntry } from "./content";
import { HelpProvider } from "./HelpProvider";
import { HelpTip } from "./HelpTip";

function Harness() {
  return (
    <HelpProvider>
      <HelpTip id="provider.kind" />
    </HelpProvider>
  );
}

describe("help system", () => {
  it("exposes a complete provider kind entry", () => {
    const entry = getHelpEntry("provider.kind");
    expect(entry.title).toBe("Provider kind");
    expect(entry.summary.length).toBeGreaterThan(20);
    expect(entry.sections.length).toBeGreaterThan(0);
  });

  it("opens the help drawer from a tip", async () => {
    renderWithTheme(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Help: Provider kind" }));
    expect(await screen.findByText(/OpenAI-compatible APIs/i)).toBeTruthy();
    fireEvent.click(screen.getByText("Learn more"));
    await waitFor(() =>
      expect(screen.getByRole("dialog", { name: "Provider kind" })).toBeTruthy(),
    );
  });
});

