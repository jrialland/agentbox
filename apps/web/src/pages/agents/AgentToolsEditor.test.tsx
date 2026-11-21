import { fireEvent, screen } from "@testing-library/react";
import { useState } from "react";
import { vi } from "vitest";

import { renderWithTheme } from "../../test/render";
import { AgentToolsEditor } from "./AgentToolsEditor";

vi.mock("../../help/HelpProvider", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../help/HelpProvider")>();
  return {
    ...actual,
    useHelp: () => ({ openHelp: vi.fn() }),
  };
});

function Harness() {
  const [value, setValue] = useState<string[]>([]);
  return <AgentToolsEditor value={value} onChange={setValue} />;
}

test("filters and selects tools", () => {
  renderWithTheme(<Harness />);
  fireEvent.change(screen.getByLabelText("Search tools"), {
    target: { value: "delete" },
  });
  expect(screen.getByText("delete_path")).toBeTruthy();
  expect(screen.queryByText("web_search")).toBeNull();
  fireEvent.click(screen.getByRole("checkbox", { name: /delete_path/i }));
  expect(screen.getByText("1 selected")).toBeTruthy();
});
