import { TextInput } from "../../design-system/forms/TextInput";
import { Checkbox } from "../../design-system/forms/Checkbox";
import { Button } from "../../design-system/primitives/Button";
import { HelpTip } from "../../help/HelpTip";
import type { AgentMode } from "./agentFormValidation";

export function AgentModesEditor({
  value,
  onChange,
  error,
}: {
  value: AgentMode[];
  onChange: (modes: AgentMode[]) => void;
  error?: string;
}) {
  function update(index: number, patch: Partial<AgentMode>) {
    onChange(value.map((mode, i) => (i === index ? { ...mode, ...patch } : mode)));
  }

  return (
    <div style={{ display: "grid", gap: 8 }}>
      <div style={{ alignItems: "center", display: "flex", gap: 8 }}>
        <strong>Modes</strong>
        <HelpTip id="agent.modes" />
      </div>
      {value.map((mode, index) => (
        <div
          key={index}
          style={{
            alignItems: "end",
            border: "1px solid var(--ab-border)",
            borderRadius: 4,
            display: "grid",
            gap: 8,
            gridTemplateColumns: "1fr auto auto",
            padding: 10,
          }}
        >
          <TextInput
            aria-label={`Mode ${index + 1} name`}
            label={`Mode ${index + 1}`}
            value={mode.name}
            onChange={(event) => update(index, { name: event.currentTarget.value })}
          />
          <Checkbox
            label="Write enabled"
            checked={mode.write}
            onChange={(event) =>
              update(index, { write: event.currentTarget.checked })
            }
          />
          <Button
            size="compact-xs"
            variant="subtle"
            color="red"
            aria-label={`Remove mode ${index + 1}`}
            onClick={() => onChange(value.filter((_, i) => i !== index))}
          >
            Remove
          </Button>
        </div>
      ))}
      {error && (
        <span role="alert" style={{ color: "var(--ab-danger)" }}>
          {error}
        </span>
      )}
      <Button
        variant="light"
        onClick={() => onChange([...value, { name: "", write: false }])}
      >
        Add mode
      </Button>
    </div>
  );
}
