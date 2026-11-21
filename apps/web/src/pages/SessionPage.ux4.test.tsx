import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";

import { ApiError } from "../api/errors";

const queries = vi.hoisted(() => ({
  useMessages: vi.fn(() => ({ data: [] })),
  useSession: vi.fn(),
  useSessionLsp: vi.fn(() => ({ data: { detected: [], active: [] } })),
  useSessionPlan: vi.fn(() => ({ data: { items: [] } })),
  useSkills: vi.fn(() => ({ data: [] })),
  useSessionFiles: vi.fn(() => ({ data: [] })),
}));

vi.mock("../api/queries", () => queries);

import { SessionPage } from "./SessionPage";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/sessions/missing"]}>
          <Routes>
            <Route path="/sessions/:id" element={<SessionPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => {
  queries.useMessages.mockClear();
  queries.useSession.mockReset();
  queries.useSessionLsp.mockClear();
  queries.useSessionPlan.mockClear();
});

test("renders session not found without the composer", () => {
  queries.useSession.mockReturnValue({
    data: undefined,
    error: new ApiError("Not found", 404),
    refetch: vi.fn(),
  });

  renderPage();

  expect(
    screen.getByRole("heading", { name: /session not found/i }),
  ).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Send" })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Session" })).not.toBeInTheDocument();
});

test("disables dependent queries after a session 404", () => {
  queries.useSession.mockReturnValue({
    data: undefined,
    error: new ApiError("Not found", 404),
    refetch: vi.fn(),
  });

  renderPage();

  expect(queries.useMessages).toHaveBeenCalledWith("missing", false);
  expect(queries.useSessionLsp).toHaveBeenCalledWith("missing", false);
  expect(queries.useSessionPlan).toHaveBeenCalledWith("missing", false, false);
});

test("renders a retryable error for a failed session read", () => {
  const refetch = vi.fn();
  queries.useSession.mockReturnValue({
    data: undefined,
    error: new ApiError("Server exploded", 500),
    refetch,
  });

  renderPage();

  expect(screen.getByText("Could not load session")).toBeInTheDocument();
  expect(screen.getByText("Server exploded")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(refetch).toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Send" })).not.toBeInTheDocument();
});
