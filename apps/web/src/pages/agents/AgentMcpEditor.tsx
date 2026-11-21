import { useState } from "react";

import { TextInput } from "../../design-system/forms/TextInput";
import { Button } from "../../design-system/primitives/Button";
import { HelpTip } from "../../help/HelpTip";
import { validateMcpUrl } from "./agentFormValidation";

export function AgentMcpEditor({
  value,
  onChange,
  error,
}: {
  value: string[];
  onChange: (servers: string[]) => void;
  error?: string;
}) {
  const [input, setInput] = useState("");
  const inputError = input ? validateMcpUrl(input) : null;

  function add() {
    if (!input || inputError) return;
    onChange([...value, input.trim()]);
    setInput("");
  }

  return (
    <div style={{ display: "grid", gap: 8 }}>
      <div style={{ alignItems: "center", display: "flex", gap: 8 }}>
        <strong>MCP servers</strong>
        <HelpTip id="agent.mcp" />
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <TextInput
          aria-label="MCP server URL"
          placeholder="https://server/mcp"
          value={input}
          error={inputError ?? undefined}
          onChange={(event) => setInput(event.currentTarget.value)}
          style={{ flex: 1 }}
        />
        <Button variant="light" onClick={add} disabled={!input || !!inputError}>
          Add
        </Button>
      </div>
      <p style={{ color: "var(--ab-text-muted)", fontSize: 12, margin: 0 }}>
        Remote MCP endpoint; authentication and transport are handled by the server.
      </p>
      <ul style={{ display: "grid", gap: 4, listStyle: "none", margin: 0, padding: 0 }}>
        {value.map((url, index) => (
          <li
            key={`${url}-${index}`}
            style={{ alignItems: "center", display: "flex", gap: 8 }}
          >
            <code style={{ flex: 1 }}>{url}</code>
            <Button
              size="compact-xs"
              variant="subtle"
              color="red"
              onClick={() => onChange(value.filter((_, i) => i !== index))}
            >
              Remove
            </Button>
          </li>
        ))}
      </ul>
      {error && (
        <span role="alert" style={{ color: "var(--ab-danger)" }}>
          {error}
        </span>
      )}
    </div>
  );
}
