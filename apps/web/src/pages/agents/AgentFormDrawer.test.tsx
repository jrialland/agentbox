import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import type { Agent } from "../../api/endpoints";
import { AgentFormDrawer } from "./AgentFormDrawer";

vi.mock("../../api/queries", () => ({
  useCreateAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useLabels: () => ({ data: [] }),
  useModels: () => ({ data: [] }),
  useProviders: () => ({ data: [] }),
  useUploadAvatar: () => ({ mutateAsync: vi.fn() }),
}));

const agent: Agent = {
  name: "coder",
  description: "desc",
  instructions: "inst",
  model_binding: { model: "m", provider: "p" },
  model_label: null,
  tool_bindings: [
    {
      server_url: "",
      tool_prefix: "",
      id: "time",
      command: "uvx",
      args: ["mcp-server-time"],
      env: {},
      env_passthrough: [],
      cwd: "",
    },
  ],
  mode_definitions: [{ name: "agent", flags: { write: true } }],
  sub_agent_ids: [],
};

describe("AgentFormDrawer", () => {
  test("prefills an existing agent for editing", () => {
    render(
      <MantineProvider>
        <AgentFormDrawer
          opened
          onClose={() => undefined}
          subAgentOptions={[]}
          agent={agent}
        />
      </MantineProvider>,
    );
    expect(screen.getByDisplayValue("coder")).toBeDisabled();
    expect(screen.getByDisplayValue("uvx")).toBeInTheDocument();
  });
});
