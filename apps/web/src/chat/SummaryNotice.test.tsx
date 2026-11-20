import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";

import { SummaryNotice } from "./SummaryNotice";

test("renders and expands the summary", () => {
  render(
    <MantineProvider>
      <SummaryNotice content="compressed history" />
    </MantineProvider>,
  );
  expect(screen.getByText("Earlier conversation summarized")).toBeInTheDocument();
  expect(screen.queryByText("compressed history")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show" }));
  expect(screen.getByText("compressed history")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Hide" })).toBeInTheDocument();
});
