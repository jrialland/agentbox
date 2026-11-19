import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { vi } from "vitest";

vi.mock("../api/queries", () => ({
  useSkills: () => ({ data: [] }),
  useSessionFiles: (_sid: string, q: string) =>
    q ? { data: ["pkg/streaming.py"] } : { data: [] },
}));

import { Composer } from "./Composer";

function Harness() {
  const [value, setValue] = useState("@stream");
  return (
    <Composer
      sessionId="s1"
      value={value}
      setValue={setValue}
      mode="agent"
      setMode={() => {}}
      running={false}
      onSend={() => {}}
      onSelectSkill={() => {}}
    />
  );
}

test("inserts a cited file path", () => {
  render(
    <MantineProvider>
      <Harness />
    </MantineProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "@pkg/streaming.py" }));
  expect(screen.getByLabelText("Message")).toHaveValue("@pkg/streaming.py ");
});
