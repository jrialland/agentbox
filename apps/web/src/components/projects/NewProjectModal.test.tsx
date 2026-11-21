import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/errors";
import { renderWithTheme } from "../../test/render";

const queries = vi.hoisted(() => ({
  useCreateProject: vi.fn(),
  useUpdateProject: vi.fn(),
}));

vi.mock("../../api/queries", () => queries);

import { NewProjectModal } from "./NewProjectModal";

function renderModal(rejection: unknown) {
  const mutateAsync = vi.fn().mockRejectedValue(rejection);
  queries.useCreateProject.mockReturnValue({ mutateAsync, isPending: false });
  queries.useUpdateProject.mockReturnValue({
    mutateAsync: vi.fn(),
    isPending: false,
  });
  renderWithTheme(<NewProjectModal opened onClose={() => {}} />);
  fireEvent.change(screen.getByLabelText("Name"), {
    target: { value: "New project" },
  });
  fireEvent.change(screen.getByLabelText("Path"), {
    target: { value: "C:\\work" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create" }));
  return mutateAsync;
}

beforeEach(() => {
  queries.useCreateProject.mockReset();
  queries.useUpdateProject.mockReset();
});

describe("NewProjectModal API errors", () => {
  it("maps 422 field errors into the form and keeps the dialog open", async () => {
    const mutateAsync = renderModal(
      new ApiError("Validation failed", 422, { name: "name is taken" }),
    );

    expect(await screen.findByText("name is taken")).toBeInTheDocument();
    expect(screen.getByText("New project")).toBeInTheDocument();
    expect(mutateAsync).toHaveBeenCalledOnce();
  });

  it("shows a form-level alert for a generic 422", async () => {
    renderModal(new ApiError("Request validation failed", 422));

    expect(
      await screen.findByText("Request validation failed"),
    ).toBeInTheDocument();
    expect(screen.getByText("New project")).toBeInTheDocument();
  });
});
