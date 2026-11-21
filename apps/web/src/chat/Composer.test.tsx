import { fireEvent, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithTheme } from "../test/render";
import { uploadAttachment } from "../api/endpoints";

vi.mock("../api/queries", () => ({
  useSkills: () => ({ data: [{ name: "review", description: "Review code" }] }),
  useSessionFiles: (_sid: string, q: string) =>
    q ? { data: ["pkg/streaming.py"] } : { data: [] },
}));

vi.mock("../api/endpoints", () => ({
  uploadAttachment: vi.fn(async () => ({
    id: "a1",
    filename: "notes.txt",
    media_type: "text/plain",
  })),
}));

import { Composer } from "./Composer";

function Harness({
  initial = "hello",
  running = false,
  onSend = vi.fn(),
  onStop = vi.fn(),
  setMode = vi.fn(),
}: {
  initial?: string;
  running?: boolean;
  onSend?: (ids: string[]) => void;
  onStop?: () => void;
  setMode?: (mode: string | null) => void;
}) {
  const [value, setValue] = useState(initial);
  return (
    <Composer
      sessionId="s1"
      value={value}
      setValue={setValue}
      mode="agent"
      setMode={setMode}
      running={running}
      onSend={onSend}
      onStop={onStop}
      onSelectSkill={() => {}}
    />
  );
}

describe("Composer", () => {
  beforeEach(() => {
    vi.mocked(uploadAttachment).mockClear();
  });

  it("inserts a cited file path", () => {
    renderWithTheme(<Harness initial="@stream" />);
    fireEvent.click(screen.getByRole("button", { name: "@pkg/streaming.py" }));
    expect(screen.getByLabelText("Message")).toHaveValue("@pkg/streaming.py ");
  });

  it("sends on Enter and preserves Shift+Enter", () => {
    const onSend = vi.fn();
    renderWithTheme(<Harness onSend={onSend} />);
    const input = screen.getByLabelText("Message");

    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();

    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith([]);
  });

  it("disables Send for empty input", () => {
    renderWithTheme(<Harness initial="" />);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("shows Stop while running", () => {
    const onStop = vi.fn();
    renderWithTheme(<Harness running onStop={onStop} />);

    expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(onStop).toHaveBeenCalled();
  });

  it("uploads picked attachments", async () => {
    renderWithTheme(<Harness />);
    const file = new File(["hello"], "notes.txt", { type: "text/plain" });

    fireEvent.change(screen.getByLabelText("Attach files"), {
      target: { files: [file] },
    });

    await waitFor(() => expect(uploadAttachment).toHaveBeenCalledWith("s1", file));
    expect(await screen.findByText("notes.txt")).toBeTruthy();
  });

  it("switches Ask/Agent mode", () => {
    const setMode = vi.fn();
    renderWithTheme(<Harness setMode={setMode} />);
    fireEvent.click(screen.getByText("Ask"));
    expect(setMode).toHaveBeenCalledWith("ask");
  });
});
