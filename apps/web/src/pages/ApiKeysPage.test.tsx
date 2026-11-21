import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, vi } from "vitest";

import * as endpoints from "../api/endpoints";
import { ApiKeysPage } from "./ApiKeysPage";

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MantineProvider>
      <QueryClientProvider client={client}>
        <ApiKeysPage />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

test("renders api keys list", async () => {
  vi.spyOn(endpoints, "fetchApiKeys").mockResolvedValue([
    {
      id: "abcdef123456",
      scopes: ["projects:read"],
      expires_at: null,
      revoked_at: null,
      created_at: "2026-01-01T00:00:00Z",
    },
  ] as never);
  renderPage();
  expect(await screen.findByText("projects:read")).toBeInTheDocument();
});

test("shows a retry state when keys fail to load", async () => {
  vi.spyOn(endpoints, "fetchApiKeys").mockRejectedValueOnce(new Error("boom"));
  renderPage();
  expect(
    await screen.findByText("Could not load API keys"),
  ).toBeInTheDocument();
});
