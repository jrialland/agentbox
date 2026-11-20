import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

vi.mock("../api/queries", () => ({
  useMessages: () => ({ data: [] }),
  useSession: () => ({ data: { agent_name: "bot" } }),
  useSessionLsp: () => ({
    data: {
      detected: ["python"],
      active: [
        {
          stack: "python",
          command: "uvx ty server",
          root: ".",
          status: "running",
          documents: 1,
        },
      ],
    },
  }),
  useSkills: () => ({ data: [] }),
  useSessionFiles: () => ({ data: [] }),
}));

import { SessionPage } from "./SessionPage";

test("shows the agent avatar and name in the chat header", () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MantineProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/sessions/s1"]}>
          <Routes>
            <Route path="/sessions/:id" element={<SessionPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
  expect(screen.getByTestId("session-agent")).toHaveTextContent("bot");
  expect(screen.getByRole("img", { name: "bot" })).toBeInTheDocument();
});

test("shows active LSP servers in the About modal", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MantineProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/sessions/s1"]}>
          <Routes>
            <Route path="/sessions/:id" element={<SessionPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "About" }));
  expect(
    await screen.findByText(/python — running \(1 docs\)/),
  ).toBeInTheDocument();
  expect(screen.getByText("uvx ty server")).toBeInTheDocument();
});

