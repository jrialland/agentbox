import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import type { PluginInfo } from "../../api/endpoints";
import { AgentPluginMcpEditor } from "./AgentPluginMcpEditor";

const globalPlugin: PluginInfo = {
  name: "acme-tools",
  version: "1.0.0",
  description: "Acme",
  scope: "global",
  project_id: null,
  enabled: true,
  valid: true,
  shadowed: false,
  author: {},
  homepage: "",
  repository: "",
  license: "",
  keywords: [],
  skills: [],
  mcp_servers: [{ name: "local", transport: "stdio" }],
  hooks: [],
  issues: [],
};

test("selects a global plugin MCP server", () => {
  const onChange = vi.fn();
  render(
    <MantineProvider>
      <AgentPluginMcpEditor
        projects={[]}
        projectId=""
        onProjectChange={vi.fn()}
        plugins={[globalPlugin]}
        value={[]}
        onChange={onChange}
      />
    </MantineProvider>,
  );

  fireEvent.click(
    screen.getByRole("checkbox", { name: /acme-tools \/ local/ }),
  );
  expect(onChange).toHaveBeenCalledWith([
    {
      plugin: "acme-tools",
      server: "local",
      project_id: null,
      id: "acme-tools:local",
    },
  ]);
});

test("project plugin servers are loaded for the selected project", () => {
  render(
    <MantineProvider>
      <AgentPluginMcpEditor
        projects={[{ id: "p1", name: "Project" }]}
        projectId="p1"
        onProjectChange={vi.fn()}
        plugins={[
          {
            ...globalPlugin,
            scope: "project",
            project_id: "p1",
            mcp_servers: [{ name: "project-local", transport: "stdio" }],
            hooks: [],
          },
        ]}
        value={[]}
        onChange={vi.fn()}
      />
    </MantineProvider>,
  );
  expect(
    screen.getByRole("checkbox", { name: /project-local/ }),
  ).toBeInTheDocument();
});
