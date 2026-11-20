import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";

import { PlanPanel } from "./PlanPanel";

const items = [
  { id: "a", position: 0, content: "write spec", status: "pending" },
  { id: "b", position: 1, content: "run tests", status: "completed" },
];

test("renders plan items and collapses", () => {
  render(
    <MantineProvider>
      <PlanPanel items={items} />
    </MantineProvider>,
  );
  expect(screen.getByTestId("plan-panel")).toBeInTheDocument();
  expect(screen.getByText("write spec")).toBeInTheDocument();
  expect(screen.getByText("completed")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Hide" }));
  expect(screen.queryByText("write spec")).not.toBeInTheDocument();
});

test("renders nothing when empty", () => {
  const { container } = render(
    <MantineProvider>
      <PlanPanel items={[]} />
    </MantineProvider>,
  );
  expect(container.querySelector('[data-testid="plan-panel"]')).toBeNull();
});
