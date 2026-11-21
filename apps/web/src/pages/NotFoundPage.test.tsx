import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { ThemeProvider } from "../design-system/theme/ThemeProvider";
import { NotFoundPage } from "./NotFoundPage";

test("renders a usable 404 page", () => {
  render(
    <ThemeProvider forceScheme="dark">
      <MemoryRouter>
        <NotFoundPage />
      </MemoryRouter>
    </ThemeProvider>,
  );
  expect(screen.getByRole("heading", { name: /page not found/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /back to home/i })).toBeInTheDocument();
});
