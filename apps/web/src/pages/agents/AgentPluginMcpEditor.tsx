import type { PluginInfo } from "../../api/endpoints";
import { Checkbox } from "../../design-system/forms/Checkbox";
import { Select } from "../../design-system/forms/Select";
import { Button } from "../../design-system/primitives/Button";
import { HelpTip } from "../../help/HelpTip";
import type { PluginMcpBindingDraft } from "./pluginMcpTypes";

function key(plugin: PluginInfo, server: string): string {
  return `${plugin.name}:${server}`;
}

export function AgentPluginMcpEditor({
  projects,
  projectId,
  onProjectChange,
  plugins,
  value,
  onChange,
  error,
}: {
  projects: { id: string; name: string }[];
  projectId: string;
  onProjectChange: (projectId: string) => void;
  plugins: PluginInfo[];
  value: PluginMcpBindingDraft[];
  onChange: (value: PluginMcpBindingDraft[]) => void;
  error?: string;
}) {
  const available = plugins.filter(
    (plugin) => plugin.enabled && plugin.valid,
  );
  const selectedKeys = new Set(
    value.map((item) => `${item.plugin}:${item.server}`),
  );
  const knownKeys = new Set(
    available.flatMap((plugin) =>
      plugin.mcp_servers.map((server) => key(plugin, server.name)),
    ),
  );

  function toggle(
    plugin: PluginInfo,
    server: string,
    checked: boolean,
  ) {
    const id = key(plugin, server);
    if (checked) {
      onChange([
        ...value,
        {
          plugin: plugin.name,
          server,
          project_id: plugin.project_id,
          id,
        },
      ]);
    } else {
      onChange(value.filter((item) => `${item.plugin}:${item.server}` !== id));
    }
  }

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div style={{ alignItems: "center", display: "flex", gap: 8 }}>
        <strong>Plugin MCP servers</strong>
        <HelpTip id="plugins.overview" />
      </div>
      <Select
        label="Project for project plugin servers"
        data={[
          { value: "", label: "Global plugins only" },
          ...projects.map((project) => ({
            value: project.id,
            label: project.name,
          })),
        ]}
        value={projectId}
        onChange={(item) => onProjectChange(item ?? "")}
      />
      {available.length === 0 ? (
        <p style={{ color: "var(--ab-text-muted)", margin: 0 }}>
          No enabled plugins with MCP servers are available in this scope.
        </p>
      ) : (
        available.map((plugin) => (
          <div key={`${plugin.scope}:${plugin.project_id ?? ""}:${plugin.name}`}>
            <div style={{ fontSize: 12, fontWeight: 600 }}>
              {plugin.name}{" "}
              <span style={{ color: "var(--ab-text-muted)" }}>
                ({plugin.scope})
              </span>
            </div>
            {plugin.mcp_servers.map((server) => {
              const id = key(plugin, server.name);
              return (
                <Checkbox
                  key={id}
                  label={`${plugin.name} / ${server.name} · ${server.transport}`}
                  checked={selectedKeys.has(id)}
                  onChange={(event) =>
                    toggle(plugin, server.name, event.currentTarget.checked)
                  }
                />
              );
            })}
          </div>
        ))
      )}
      {value.length ? (
        <div>
          <strong style={{ fontSize: 12 }}>Selected plugin servers</strong>
          <ul style={{ margin: 0 }}>
            {value.map((item) => {
              const id = `${item.plugin}:${item.server}`;
              const stale = !knownKeys.has(id);
              return (
                <li key={id}>
                  <code>{id}</code>
                  {item.project_id ? ` · project ${item.project_id}` : " · global"}
                  {stale ? " · unavailable" : ""}
                  <Button
                    size="compact-xs"
                    variant="subtle"
                    color="red"
                    onClick={() =>
                      onChange(
                        value.filter(
                          (entry) =>
                            `${entry.plugin}:${entry.server}` !== id,
                        ),
                      )
                    }
                  >
                    Remove
                  </Button>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
      {error && (
        <span role="alert" style={{ color: "var(--ab-danger)" }}>
          {error}
        </span>
      )}
    </div>
  );
}
