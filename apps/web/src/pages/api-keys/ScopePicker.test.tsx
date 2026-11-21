import { fireEvent, screen } from "@testing-library/react";
import { useState } from "react";
import { vi } from "vitest";

import { renderWithTheme } from "../../test/render";
import { ScopePicker } from "./ScopePicker";

vi.mock("../../help/HelpProvider", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../help/HelpProvider")>();
  return { ...actual, useHelp: () => ({ openHelp: vi.fn() }) };
});

function Harness() {
  const [value, setValue] = useState<string[]>([]);
  return (
    <ScopePicker
      available={["sessions:create", "sessions:read", "providers:read", "api_keys:manage"]}
      value={value}
      onChange={setValue}
    />
  );
}

test("warns when no scopes are selected and recommends defaults", () => {
  renderWithTheme(<Harness />);
  expect(screen.getByText(/unusable/i)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Use recommended" }));
  expect(screen.getByText("2 selected")).toBeTruthy();
});

