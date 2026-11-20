import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithTheme } from "../../test/render";
import { CodeBlock } from "./CodeBlock";
import { CopyButton } from "./CopyButton";
import { Spinner } from "./Spinner";

describe("feedback primitives", () => {
  it("renders a spinner with a label", () => {
    renderWithTheme(<Spinner label="Thinking" />);
    expect(screen.getByLabelText("Thinking")).toBeInTheDocument();
  });

  it("renders code with a language label", () => {
    render(<CodeBlock code="const x = 1;" language="ts" />);
    expect(screen.getByText("ts")).toBeInTheDocument();
    expect(screen.getByText("const x = 1;")).toBeInTheDocument();
  });

  it("copies a value and shows confirmation", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<CopyButton value="hello" />);
    fireEvent.click(screen.getByRole("button", { name: /copy/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("hello"));
    expect(screen.getByText("Copied")).toBeInTheDocument();
  });
});
