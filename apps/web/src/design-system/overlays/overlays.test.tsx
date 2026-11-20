import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithTheme } from "../../test/render";
import { ConfirmDialog } from "./ConfirmDialog";

describe("ConfirmDialog", () => {
  it("calls onConfirm from the confirm button", () => {
    const onConfirm = vi.fn();
    renderWithTheme(
      <ConfirmDialog
        opened
        title="Delete project?"
        description="This cannot be undone."
        confirmLabel="Delete"
        danger
        onConfirm={onConfirm}
        onClose={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });
});
