import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { SessionPage } from "./SessionPage";

test("shows the session id", () => {
  render(
    <MemoryRouter initialEntries={["/sessions/abc123"]}>
      <Routes>
        <Route path="/sessions/:id" element={<SessionPage />} />
      </Routes>
    </MemoryRouter>,
  );
  expect(screen.getByText(/abc123/)).toBeInTheDocument();
});
