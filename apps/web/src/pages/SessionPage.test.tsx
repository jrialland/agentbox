import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

import * as endpoints from "../api/endpoints";
import { SessionPage } from "./SessionPage";

test("renders the chat composer", async () => {
  vi.spyOn(endpoints, "fetchMessages").mockResolvedValue([]);
  vi.spyOn(endpoints, "fetchSession").mockResolvedValue({
    agent_name: "bot",
  } as never);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MantineProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/sessions/abc"]}>
          <Routes>
            <Route path="/sessions/:id" element={<SessionPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
  expect(
    await screen.findByRole("heading", { name: "Untitled session" }),
  ).toBeInTheDocument();
  expect(screen.getByText("Start the conversation")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument();
});

test("renders a summary notice", async () => {
  vi.spyOn(endpoints, "fetchMessages").mockResolvedValue([
    { id: "sum", role: "summary", content: "compressed", parent_id: null },
  ] as never);
  vi.spyOn(endpoints, "fetchSession").mockResolvedValue({
    agent_name: "bot",
  } as never);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MantineProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/sessions/abc"]}>
          <Routes>
            <Route path="/sessions/:id" element={<SessionPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
  expect(
    await screen.findByText("Earlier conversation summarized"),
  ).toBeInTheDocument();
});
