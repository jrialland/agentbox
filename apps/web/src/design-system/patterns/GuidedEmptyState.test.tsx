import { fireEvent, screen, waitFor } from "@testing-library/react";
import { RiRobot2Line } from "@remixicon/react";

import { HelpProvider } from "../../help/HelpProvider";
import { renderWithTheme } from "../../test/render";
import { GuidedEmptyState } from "./GuidedEmptyState";

test("shows a CTA and help link", async () => {
  renderWithTheme(
    <HelpProvider>
      <GuidedEmptyState
        icon={RiRobot2Line}
        title="No agents"
        description="Create an agent to start."
        action={<button type="button">Create agent</button>}
        helpId="agent.tools"
      />
    </HelpProvider>,
  );
  expect(screen.getByText("No agents")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Learn about Agent tools" }));
  await waitFor(() =>
    expect(screen.getByRole("dialog", { name: "Agent tools" })).toBeTruthy(),
  );
});

