import { fireEvent, screen, waitFor } from "@testing-library/react";
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

  it("type-to-confirm stays disabled until the exact name is entered", async () => {
    const onConfirm = vi.fn();
    renderWithTheme(
      <ConfirmDialog
        opened
        title="Delete project?"
        description="This cannot be undone."
        requireText="Demo"
        confirmLabel="Delete"
        danger
        onConfirm={onConfirm}
        onClose={() => {}}
      />,
    );
    const confirm = screen.getByRole("button", { name: "Delete" });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/type Demo/i), { target: { value: "Demo" } });
    expect(confirm).not.toBeDisabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(onConfirm).toHaveBeenCalled());
  });

  it("allows confirming without typing when requireText is omitted", () => {
    const onConfirm = vi.fn();
    renderWithTheme(
      <ConfirmDialog
        opened
        title="Archive project?"
        description="You can restore it later."
        confirmLabel="Archive"
        onConfirm={onConfirm}
        onClose={() => {}}
      />,
    );
    const confirm = screen.getByRole("button", { name: "Archive" });
    expect(confirm).not.toBeDisabled();
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("keeps the dialog open and shows the API error when the mutation fails", async () => {
    const onConfirm = vi.fn().mockRejectedValue(new Error("Project is in use."));
    renderWithTheme(
      <ConfirmDialog
        opened
        title="Delete project?"
        description="This cannot be undone."
        requireText="Demo"
        confirmLabel="Delete"
        danger
        onConfirm={onConfirm}
        onClose={() => {}}
      />,
    );
    fireEvent.change(screen.getByLabelText(/type Demo/i), { target: { value: "Demo" } });
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Project is in use.");
    expect(screen.getByText("Delete project?")).toBeInTheDocument();
  });

  it("disables the confirm button while the mutation is pending", async () => {
    let resolve: () => void = () => {};
    const onConfirm = vi.fn(
      () =>
        new Promise<void>((done) => {
          resolve = done;
        }),
    );
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
    await waitFor(() => expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled());
    resolve();
    await waitFor(() => expect(screen.getByRole("button", { name: "Delete" })).not.toBeDisabled());
  });
});
