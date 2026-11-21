import { Checkbox } from "../../design-system/forms/Checkbox";
import { Badge } from "../../design-system/primitives/Badge";
import { Button } from "../../design-system/primitives/Button";
import { HelpTip } from "../../help/HelpTip";
import { describeScope, RECOMMENDED_SCOPES } from "./scopeHelp";

const GROUP_LABELS: Record<string, string> = {
  agents: "Agents",
  providers: "Providers",
  projects: "Projects",
  sessions: "Sessions",
  users: "Admin",
  roles: "Admin",
  api_keys: "Admin",
};

export function ScopePicker({
  available,
  value,
  onChange,
}: {
  available: string[];
  value: string[];
  onChange: (scopes: string[]) => void;
}) {
  const groups = new Map<string, string[]>();
  for (const scope of available) {
    const prefix = scope.split(":")[0];
    const label = GROUP_LABELS[prefix] ?? "Other";
    groups.set(label, [...(groups.get(label) ?? []), scope]);
  }

  return (
    <div style={{ display: "grid", gap: 8 }}>
      <div style={{ alignItems: "center", display: "flex", gap: 8 }}>
        <Badge tone={value.length > 0 ? "success" : "warning"}>
          {value.length} selected
        </Badge>
        <Button
          size="compact-xs"
          variant="light"
          onClick={() =>
            onChange(RECOMMENDED_SCOPES.filter((scope) => available.includes(scope)))
          }
        >
          Use recommended
        </Button>
        <Button size="compact-xs" variant="light" onClick={() => onChange([])}>
          Clear scopes
        </Button>
        <HelpTip id="api.scopes" />
      </div>
      {value.length === 0 && (
        <p role="alert" style={{ color: "var(--ab-amber)", margin: 0 }}>
          No scopes selected. The key is unusable until you add at least one.
        </p>
      )}
      {[...groups.entries()].map(([label, scopes]) => (
        <div
          key={label}
          style={{
            border: "1px solid var(--ab-border)",
            borderRadius: 4,
            padding: 10,
          }}
        >
          <strong style={{ fontSize: 12 }}>{label}</strong>
          <div style={{ display: "grid", gap: 6, marginTop: 6 }}>
            {scopes.map((scope) => (
              <div key={scope} style={{ display: "grid", gap: 2 }}>
                <Checkbox
                  label={scope}
                  checked={value.includes(scope)}
                  onChange={(event) =>
                    onChange(
                      event.currentTarget.checked
                        ? [...new Set([...value, scope])]
                        : value.filter((item) => item !== scope),
                    )
                  }
                />
                <span style={{ color: "var(--ab-text-muted)", fontSize: 12 }}>
                  {describeScope(scope)}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

