import { useMemo, useState } from "react";

import { Checkbox } from "../../design-system/forms/Checkbox";
import { TextInput } from "../../design-system/forms/TextInput";
import { Badge } from "../../design-system/primitives/Badge";
import { Button } from "../../design-system/primitives/Button";
import { Section } from "../../design-system/primitives/Section";
import { HelpTip } from "../../help/HelpTip";
import { TOOL_GROUPS, TOOL_META, type ToolCategory } from "./toolCatalog";

const ADVANCED_TOOLS = new Set(["delete_path", "move_file", "copy_file", "terminal"]);

export function AgentToolsEditor({
  value,
  onChange,
}: {
  value: string[];
  onChange: (tools: string[]) => void;
}) {
  const [query, setQuery] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return Object.values(TOOL_META).filter((tool) => {
      if (!showAdvanced && !needle && ADVANCED_TOOLS.has(tool.name)) return false;
      if (!needle) return true;
      return `${tool.name} ${tool.label} ${tool.description}`
        .toLowerCase()
        .includes(needle);
    });
  }, [query, showAdvanced]);

  function toggle(name: string, checked: boolean) {
    onChange(
      checked
        ? [...new Set([...value, name])]
        : value.filter((tool) => tool !== name),
    );
  }

  function groupTools(category: ToolCategory) {
    return visible.filter((tool) => tool.category === category);
  }

  return (
    <div>
      <div
        style={{
          alignItems: "center",
          display: "flex",
          flexWrap: "wrap",
          gap: 8,
          marginBottom: 12,
        }}
      >
        <TextInput
          aria-label="Search tools"
          placeholder="Search tools"
          value={query}
          onChange={(event) => setQuery(event.currentTarget.value)}
          style={{ flex: "1 1 220px" }}
        />
        <Badge tone={value.length > 0 ? "success" : "neutral"}>
          {value.length} selected
        </Badge>
        <Button
          size="compact-xs"
          variant="light"
          onClick={() =>
            onChange([...new Set([...value, ...visible.map((tool) => tool.name)])])
          }
        >
          Select all
        </Button>
        <Button size="compact-xs" variant="light" onClick={() => onChange([])}>
          Clear
        </Button>
        <Checkbox
          label="Show advanced"
          checked={showAdvanced}
          onChange={(event) => setShowAdvanced(event.currentTarget.checked)}
        />
        <HelpTip id="agent.tools" />
      </div>

      {TOOL_GROUPS.map((group) => {
        const tools = groupTools(group.category);
        if (tools.length === 0) return null;
        return (
          <Section key={group.category} title={group.title}>
            <p style={{ color: "var(--ab-text-muted)", marginTop: 0 }}>
              {group.description}
            </p>
            <div
              style={{
                display: "grid",
                gap: "6px 16px",
                gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
              }}
            >
              {tools.map((tool) => (
                <div
                  key={tool.name}
                  style={{ alignItems: "start", display: "flex", gap: 8 }}
                >
                  <Checkbox
                    aria-label={tool.name}
                    checked={value.includes(tool.name)}
                    onChange={(event) =>
                      toggle(tool.name, event.currentTarget.checked)
                    }
                  />
                  <div style={{ display: "grid", gap: 2 }}>
                    <code>{tool.name}</code>
                    <span style={{ color: "var(--ab-text-muted)", fontSize: 12 }}>
                      {tool.description}
                    </span>
                    <Badge tone={tool.risk === "write" ? "warning" : "neutral"}>
                      {tool.risk}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </Section>
        );
      })}
    </div>
  );
}

