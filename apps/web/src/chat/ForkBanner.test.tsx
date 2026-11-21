import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithTheme } from "../test/render";
import { ForkBanner } from "./ForkBanner";

describe("ForkBanner", () => {
  it("shows edit copy and cancels edit mode", () => {
    const onCancel = vi.fn();
    renderWithTheme(<ForkBanner onCancel={onCancel} />);

    expect(
      screen.getByText("Editing from this turn - sending creates a new branch"),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cancel edit" }));
    expect(onCancel).toHaveBeenCalled();
  });
});
