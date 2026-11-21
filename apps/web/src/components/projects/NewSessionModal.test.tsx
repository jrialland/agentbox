import { fireEvent, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/errors";
import { renderWithTheme } from "../../test/render";

const queries = vi.hoisted(() => ({
  useAgents: vi.fn(),
  useCreateSession: vi.fn(),
}));

vi.mock("../../api/queries", () => queries);

vi.mock("../../design-system/forms/Select", () => ({
  Select: ({
    data,
    value,
    onChange,
  }: {
    data: string[];
    value: string | null;
    onChange: (value: string | null) => void;
  }) => (
    <select
      aria-label="Agent"
      value={value ?? ""}
      onChange={(event) => onChange(event.currentTarget.value || null)}
    >
      <option value="">Select an agent</option>
      {data.map((item) => (
        <option key={item} value={item}>
          {item}
        </option>
      ))}
    </select>
  ),
}));

import { NewSessionModal } from "./NewSessionModal";

function renderModal(rejection: unknown) {
  const mutateAsync = vi.fn().mockRejectedValue(rejection);
  queries.useAgents.mockReturnValue({ data: [{ name: "bot" }] });
  queries.useCreateSession.mockReturnValue({
    mutateAsync,
    isPending: false,
  });
  renderWithTheme(
    <MemoryRouter>
      <NewSessionModal opened onClose={() => {}} projectId="p1" />
    </MemoryRouter>,
  );
  fireEvent.change(screen.getByLabelText("Agent"), {
    target: { value: "bot" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create" }));
  return mutateAsync;
}

beforeEach(() => {
  queries.useAgents.mockReset();
  queries.useCreateSession.mockReset();
});

describe("NewSessionModal API errors", () => {
  it("maps 422 field errors into the agent field and keeps the dialog open", async () => {
    const mutateAsync = renderModal(
      new ApiError("Validation failed", 422, {
        agent_id: "agent is required",
      }),
    );

    expect(await screen.findByText("agent is required")).toBeInTheDocument();
    expect(screen.getByText("New session")).toBeInTheDocument();
    expect(mutateAsync).toHaveBeenCalledOnce();
  });

  it("shows a form-level alert for a generic 422", async () => {
    renderModal(new ApiError("Request validation failed", 422));

    expect(
      await screen.findByText("Request validation failed"),
    ).toBeInTheDocument();
    expect(screen.getByText("New session")).toBeInTheDocument();
  });
});
