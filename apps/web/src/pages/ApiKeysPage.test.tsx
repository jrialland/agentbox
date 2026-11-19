import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("../api/queries", () => ({
  useApiKeys: () => ({
    data: [
      {
        id: "abcdef123456",
        scopes: ["projects:read"],
        expires_at: null,
        revoked_at: null,
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
  }),
  useCreateApiKey: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRevokeApiKey: () => ({ mutateAsync: vi.fn() }),
}));

import { ApiKeysPage } from "./ApiKeysPage";

test("renders api keys list", () => {
  render(
    <MantineProvider>
      <ApiKeysPage />
    </MantineProvider>,
  );
  expect(screen.getByText("projects:read")).toBeInTheDocument();
});
