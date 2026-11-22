import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

const mutateAsync = vi.fn();

vi.mock("../api/queries", () => ({
  useProjects: () => ({ data: [] }),
  usePlugins: () => ({
    data: [
      {
        name: "acme-tools",
        version: "1.0.0",
        description: "Acme tools",
        scope: "global",
        project_id: null,
        enabled: false,
        valid: true,
        shadowed: false,
        author: {},
        homepage: "",
        repository: "",
        license: "",
        keywords: [],
        skills: [{ name: "acme-tools:review", description: "Review" }],
        mcp_servers: [{ name: "local", transport: "stdio" }],
        issues: [],
      },
    ],
    error: undefined,
    refetch: vi.fn(),
  }),
  useSetPluginState: () => ({ mutateAsync, isPending: false }),
}));

import { PluginsPage } from "./PluginsPage";

test("enables a plugin after the trust confirmation", async () => {
  mutateAsync.mockResolvedValue({});
  render(
    <MantineProvider>
      <PluginsPage />
    </MantineProvider>,
  );

  expect(await screen.findByText("acme-tools")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Enable" }));
  expect(
    await screen.findByText(/Only enable plugins you trust/),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Enable and trust" }));

  await waitFor(() =>
    expect(mutateAsync).toHaveBeenCalledWith({
      plugin_name: "acme-tools",
      scope: "global",
      project_id: null,
      enabled: true,
    }),
  );
});
