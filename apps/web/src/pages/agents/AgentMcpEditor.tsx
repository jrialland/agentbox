import { RiAddLine } from "@remixicon/react";

import { TextInput } from "../../design-system/forms/TextInput";
import { Button } from "../../design-system/primitives/Button";
import { HelpTip } from "../../help/HelpTip";
import { emptyMcpServer, type McpServerDraft } from "./mcpTypes";

const update = (
  value: McpServerDraft[],
  index: number,
  patch: Partial<McpServerDraft>,
): McpServerDraft[] =>
  value.map((item, i) => (i === index ? { ...item, ...patch } : item));

export function AgentMcpEditor({
  value,
  onChange,
  error,
}: {
  value: McpServerDraft[];
  onChange: (servers: McpServerDraft[]) => void;
  error?: string;
}) {
  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div style={{ alignItems: "center", display: "flex", gap: 8 }}>
        <strong>MCP servers</strong>
        <HelpTip id="agent.mcp" />
      </div>
      {value.map((server, index) => (
        <div
          key={index}
          style={{
            border: "1px solid var(--ab-border)",
            display: "grid",
            gap: 8,
            padding: 12,
          }}
        >
          <div style={{ display: "flex", gap: 8 }}>
            <select
              aria-label={`MCP transport ${index + 1}`}
              value={server.kind}
              onChange={(event) =>
                onChange(
                  update(value, index, {
                    kind: event.currentTarget.value as "remote" | "stdio",
                  }),
                )
              }
            >
              <option value="remote">Remote URL</option>
              <option value="stdio">Local command</option>
            </select>
            <TextInput
              aria-label={`MCP name ${index + 1}`}
              placeholder="Name"
              value={server.id}
              onChange={(event) =>
                onChange(update(value, index, { id: event.currentTarget.value }))
              }
              style={{ flex: 1 }}
            />
            <Button
              size="compact-sm"
              variant="subtle"
              color="red"
              onClick={() => onChange(value.filter((_, i) => i !== index))}
            >
              Remove
            </Button>
          </div>
          {server.kind === "remote" ? (
            <TextInput
              aria-label={`MCP URL ${index + 1}`}
              placeholder="https://server/mcp"
              value={server.server_url}
              onChange={(event) =>
                onChange(
                  update(value, index, { server_url: event.currentTarget.value }),
                )
              }
            />
          ) : (
            <>
              <TextInput
                aria-label={`MCP command ${index + 1}`}
                placeholder="uvx"
                value={server.command}
                onChange={(event) =>
                  onChange(
                    update(value, index, { command: event.currentTarget.value }),
                  )
                }
              />
              <textarea
                aria-label={`MCP args ${index + 1}`}
                placeholder="One argument per line"
                value={server.args}
                onChange={(event) =>
                  onChange(
                    update(value, index, { args: event.currentTarget.value }),
                  )
                }
              />
              <TextInput
                aria-label={`MCP cwd ${index + 1}`}
                placeholder="cwd (defaults to project root)"
                value={server.cwd}
                onChange={(event) =>
                  onChange(
                    update(value, index, { cwd: event.currentTarget.value }),
                  )
                }
              />
              {server.env.map((row, rowIndex) => (
                <div key={rowIndex} style={{ display: "flex", gap: 8 }}>
                  <TextInput
                    aria-label={`MCP env name ${index + 1}-${rowIndex + 1}`}
                    placeholder="NAME"
                    value={row.name}
                    onChange={(event) => {
                      const env = server.env.map((item, i) =>
                        i === rowIndex
                          ? { ...item, name: event.currentTarget.value }
                          : item,
                      );
                      onChange(update(value, index, { env }));
                    }}
                  />
                  <TextInput
                    aria-label={`MCP env value ${index + 1}-${rowIndex + 1}`}
                    placeholder="value"
                    type="password"
                    value={row.value}
                    onChange={(event) => {
                      const env = server.env.map((item, i) =>
                        i === rowIndex
                          ? { ...item, value: event.currentTarget.value }
                          : item,
                      );
                      onChange(update(value, index, { env }));
                    }}
                  />
                </div>
              ))}
              <Button
                variant="light"
                size="compact-sm"
                onClick={() =>
                  onChange(
                    update(value, index, {
                      env: [...server.env, { name: "", value: "" }],
                    }),
                  )
                }
              >
                Add env
              </Button>
              <TextInput
                aria-label={`MCP env passthrough ${index + 1}`}
                placeholder="Host env names, comma separated"
                value={server.envPassthrough}
                onChange={(event) =>
                  onChange(
                    update(value, index, {
                      envPassthrough: event.currentTarget.value,
                    }),
                  )
                }
              />
              <p style={{ color: "var(--ab-text-muted)", fontSize: 12, margin: 0 }}>
                Local commands run on this machine; cwd is sandboxed to the project
                and its extra roots.
              </p>
            </>
          )}
        </div>
      ))}
      <Button
        variant="light"
        onClick={() => onChange([...value, emptyMcpServer()])}
      >
        <RiAddLine size={16} /> Add MCP server
      </Button>
      {error && (
        <span role="alert" style={{ color: "var(--ab-danger)" }}>
          {error}
        </span>
      )}
    </div>
  );
}
