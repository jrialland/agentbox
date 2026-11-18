import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { useAuthStore } from "../../store/auth";
import { RequireAuth } from "./RequireAuth";

beforeEach(() => useAuthStore.getState().clear());

test("redirects to login when unauthenticated", () => {
  render(
    <MemoryRouter initialEntries={["/secret"]}>
      <Routes>
        <Route path="/login" element={<div>Login page</div>} />
        <Route element={<RequireAuth />}>
          <Route path="/secret" element={<div>Secret</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
  expect(screen.getByText("Login page")).toBeInTheDocument();
});

test("renders the outlet when authenticated", () => {
  useAuthStore.getState().setToken("tok");
  render(
    <MemoryRouter initialEntries={["/secret"]}>
      <Routes>
        <Route path="/login" element={<div>Login page</div>} />
        <Route element={<RequireAuth />}>
          <Route path="/secret" element={<div>Secret</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
  expect(screen.getByText("Secret")).toBeInTheDocument();
});
