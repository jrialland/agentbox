import { fireEvent, screen } from "@testing-library/react";
import { useState } from "react";
import { vi } from "vitest";

import { renderWithTheme } from "../../test/render";
import { AgentModesEditor } from "./AgentModesEditor";

vi.mock("../../help/HelpProvider", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../help/HelpProvider")>();
  return { ...actual, useHelp: () => ({ openHelp: vi.fn() }) };
});

function Harness() {
  const [value, setValue] = useState([{ name: "ask", write: false }]);
  return <AgentModesEditor value={value} onChange={setValue} />;
}

test("adds and removes a mode", () => {
  renderWithTheme(<Harness />);
  fireEvent.click(screen.getByRole("button", { name: "Add mode" }));
  expect(screen.getByLabelText("Mode 2 name")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Remove mode 2" }));
  expect(screen.getByDisplayValue("ask")).toBeTruthy();
});

