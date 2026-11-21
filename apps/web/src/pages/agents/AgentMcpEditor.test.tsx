import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, test, vi } from "vitest";

import { AgentMcpEditor } from "./AgentMcpEditor";
import { emptyMcpServer, type McpServerDraft } from "./mcpTypes";

function Harness({ onChange }: { onChange: (servers: McpServerDraft[]) => void }) {
  const [value, setValue] = useState<McpServerDraft[]>([emptyMcpServer()]);
  return (
    <AgentMcpEditor
      value={value}
      onChange={(next) => {
        setValue(next);
        onChange(next);
      }}
    />
  );
}

describe("AgentMcpEditor", () => {
  test("reports changes for a stdio server", () => {
    const onChange = vi.fn();
    render(
      <MantineProvider>
        <Harness onChange={onChange} />
      </MantineProvider>,
    );
    fireEvent.change(screen.getByLabelText("MCP transport 1"), {
      target: { value: "stdio" },
    });
    fireEvent.change(screen.getByLabelText("MCP name 1"), {
      target: { value: "time" },
    });
    fireEvent.change(screen.getByLabelText("MCP command 1"), {
      target: { value: "uvx" },
    });
    fireEvent.change(screen.getByLabelText("MCP args 1"), {
      target: { value: "mcp-server-time" },
    });
    expect(onChange).toHaveBeenCalled();
    expect(screen.getByLabelText("MCP command 1")).toHaveValue("uvx");
  });
});
