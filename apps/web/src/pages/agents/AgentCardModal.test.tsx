import { fireEvent, screen } from "@testing-library/react";
import { vi } from "vitest";

const card = vi.hoisted(() => ({
  name: "Reviewer",
  description: "Reviews",
  version: "1.0.0",
  skills: [],
}));

vi.mock("../../api/queries", () => ({
  useAgentCard: () => ({ data: card }),
  useSetAgentCard: () => ({ mutateAsync: vi.fn() }),
  useDeleteAgentCard: () => ({ mutateAsync: vi.fn() }),
}));

import { AgentCardModal } from "./AgentCardModal";
import { HelpProvider } from "../../help/HelpProvider";
import { renderWithTheme } from "../../test/render";

test("edits core A2A fields and switches to JSON", () => {
  renderWithTheme(
    <HelpProvider>
      <AgentCardModal name="Reviewer" onClose={() => {}} />
    </HelpProvider>,
  );
  expect(screen.getByLabelText("Agent card name")).toHaveValue("Reviewer");
  expect(screen.getByText("Capabilities")).toBeTruthy();
  fireEvent.click(screen.getByRole("tab", { name: "JSON" }));
  expect((screen.getByLabelText("Agent card JSON") as HTMLTextAreaElement).value).toContain(
    "Reviewer",
  );
});

