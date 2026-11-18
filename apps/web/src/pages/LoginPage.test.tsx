import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

import { api } from "../api/client";
import { useAuthStore } from "../store/auth";
import { LoginPage } from "./LoginPage";

beforeEach(() => {
  useAuthStore.getState().clear();
});

test("logs in, stores token+user, and redirects", async () => {
  vi.spyOn(api, "POST").mockResolvedValue({
    data: { access_token: "tok", token_type: "bearer" },
    response: new Response(null, { status: 200 }),
  } as never);
  vi.spyOn(api, "GET").mockResolvedValue({
    data: { id: "u1", username: "alice", permissions: [] },
    response: new Response(null, { status: 200 }),
  } as never);

  render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<div>Home</div>} />
      </Routes>
    </MemoryRouter>,
  );

  fireEvent.change(screen.getByLabelText("Username"), { target: { value: "alice" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw" } });
  fireEvent.click(screen.getByRole("button", { name: "Log in" }));

  await waitFor(() => expect(useAuthStore.getState().token).toBe("tok"));
  await waitFor(() => expect(screen.getByText("Home")).toBeInTheDocument());
});

test("shows an error on bad credentials", async () => {
  vi.spyOn(api, "POST").mockResolvedValue({
    error: { detail: "Invalid credentials" },
    response: new Response(null, { status: 401 }),
  } as never);

  render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
      </Routes>
    </MemoryRouter>,
  );

  fireEvent.change(screen.getByLabelText("Username"), { target: { value: "alice" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "bad" } });
  fireEvent.click(screen.getByRole("button", { name: "Log in" }));

  await waitFor(() => expect(screen.getByText("Invalid credentials")).toBeInTheDocument());
});
