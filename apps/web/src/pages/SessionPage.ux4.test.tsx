import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";

import { ApiError } from "../api/errors";

type QueryStub = {
  data?: unknown;
  error?: Error | null;
  isSuccess?: boolean;
  refetch?: () => void;
};

const queries = vi.hoisted(() => ({
  useMessages: vi.fn((..._args: [string, boolean?]): QueryStub => ({ data: [] })),
  useSession: vi.fn((..._args: [string]): QueryStub => ({ data: undefined })),
  useSessionLsp: vi.fn(
    (..._args: [string, boolean?]): QueryStub => ({
      data: { detected: [], active: [] },
    }),
  ),
  useSessionPlan: vi.fn(
    (..._args: [string, boolean?, boolean?]): QueryStub => ({
      data: { items: [] },
    }),
  ),
  useSkills: vi.fn(() => ({ data: [] })),
  useSessionFiles: vi.fn(() => ({ data: [] })),
  useRenameSession: vi.fn(() => ({ mutateAsync: vi.fn() })),
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

const loadedSession = () => ({
  data: { agent_name: "bot" },
  isSuccess: true,
});

beforeEach(() => {
  queries.useMessages.mockReset().mockReturnValue({ data: [] });
  queries.useSession.mockReset();
  queries.useSessionLsp
    .mockReset()
    .mockReturnValue({ data: { detected: [], active: [] } });
  queries.useSessionPlan.mockReset().mockReturnValue({ data: { items: [] } });
});

test("renders session not found without the composer", () => {
  queries.useSession.mockReturnValue({
    data: undefined,
    isSuccess: false,
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
    isSuccess: false,
    error: new ApiError("Not found", 404),
    refetch: vi.fn(),
  });

  renderPage();

  expect(queries.useMessages).toHaveBeenLastCalledWith("missing", false);
  expect(queries.useSessionLsp).toHaveBeenLastCalledWith("missing", false);
  expect(queries.useSessionPlan).toHaveBeenLastCalledWith("missing", false, false);
  expect(
    queries.useMessages.mock.calls.some(([, enabled]) => enabled === true),
  ).toBe(false);
  expect(
    queries.useSessionLsp.mock.calls.some(([, enabled]) => enabled === true),
  ).toBe(false);
  expect(
    queries.useSessionPlan.mock.calls.some(([, , enabled]) => enabled === true),
  ).toBe(false);
});

test("keeps dependent queries disabled until the session loads", () => {
  queries.useSession.mockReturnValue({ data: undefined, isSuccess: false });

  renderPage();

  expect(
    queries.useMessages.mock.calls.every(([, enabled]) => enabled === false),
  ).toBe(true);
  expect(
    queries.useSessionLsp.mock.calls.every(([, enabled]) => enabled === false),
  ).toBe(true);
  expect(
    queries.useSessionPlan.mock.calls.every(([, , enabled]) => enabled === false),
  ).toBe(true);
});

test("enables dependent queries once the session loads", () => {
  queries.useSession.mockReturnValue(loadedSession());

  renderPage();

  expect(queries.useMessages).toHaveBeenLastCalledWith("missing", true);
  expect(queries.useSessionLsp).toHaveBeenLastCalledWith("missing", true);
  expect(queries.useSessionPlan).toHaveBeenLastCalledWith("missing", false, true);
});

test("renders a retryable error for a failed session read", () => {
  const refetch = vi.fn();
  queries.useSession.mockReturnValue({
    data: undefined,
    isSuccess: false,
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

test("renders a retryable error instead of the empty transcript", () => {
  const refetch = vi.fn();
  queries.useSession.mockReturnValue(loadedSession());
  queries.useMessages.mockReturnValue({
    data: undefined,
    error: new ApiError("Could not load messages", 500),
    refetch,
  });

  renderPage();

  expect(screen.getByTestId("messages-error")).toHaveTextContent(
    "Could not load messages",
  );
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(refetch).toHaveBeenCalled();
});

test("renders a compact retryable error for a failed plan read", () => {
  const refetch = vi.fn();
  queries.useSession.mockReturnValue(loadedSession());
  queries.useSessionPlan.mockReturnValue({
    data: undefined,
    error: new ApiError("Could not load plan", 500),
    refetch,
  });

  renderPage();

  const planError = screen.getByTestId("plan-error");
  expect(planError).toHaveTextContent("Could not load plan");
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(refetch).toHaveBeenCalled();
});

test("surfaces an LSP read failure in the About panel", async () => {
  const refetch = vi.fn();
  queries.useSession.mockReturnValue(loadedSession());
  queries.useSessionLsp.mockReturnValue({
    data: undefined,
    error: new ApiError("Could not load language servers", 500),
    refetch,
  });

  renderPage();

  fireEvent.click(screen.getByRole("button", { name: "About" }));
  expect(await screen.findByTestId("lsp-error")).toHaveTextContent(
    "Could not load language servers",
  );
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(refetch).toHaveBeenCalled();
});
