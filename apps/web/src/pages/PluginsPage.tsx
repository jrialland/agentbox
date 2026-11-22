import { notifications } from "@mantine/notifications";
import { RiPlugLine } from "@remixicon/react";
import { useState } from "react";

import type { PluginInfo } from "../api/endpoints";
import {
  usePlugins,
  useProjects,
  useSetPluginState,
} from "../api/queries";
import { DataTable } from "../design-system/data/DataTable";
import { Select } from "../design-system/forms/Select";
import { Drawer } from "../design-system/overlays/Drawer";
import { ConfirmDialog } from "../design-system/overlays/ConfirmDialog";
import { ErrorState } from "../design-system/patterns/ErrorState";
import { GuidedEmptyState } from "../design-system/patterns/GuidedEmptyState";
import { ListPage } from "../design-system/patterns/ListPage";
import { Button } from "../design-system/primitives/Button";
import { Panel } from "../design-system/primitives/Panel";
import { StatusChip } from "../design-system/primitives/StatusChip";

export function PluginsPage() {
  const projects = useProjects();
  const [projectId, setProjectId] = useState("");
  const { data: plugins, error, refetch } = usePlugins(
    projectId || undefined,
  );
  const setState = useSetPluginState();
  const [pending, setPending] = useState<PluginInfo | null>(null);
  const [detail, setDetail] = useState<PluginInfo | null>(null);

  const projectOptions = [
    { value: "", label: "Global plugins only" },
    ...(projects.data ?? []).map((project) => ({
      value: project.id,
      label: project.name,
    })),
  ];

  async function confirmToggle() {
    if (!pending) return;
    try {
      await setState.mutateAsync({
        plugin_name: pending.name,
        scope: pending.scope,
        project_id: pending.project_id,
        enabled: !pending.enabled,
      });
      setPending(null);
    } catch (err) {
      notifications.show({
        message:
          err instanceof Error ? err.message : "Failed to update plugin",
        color: "red",
      });
    }
  }

  return (
    <ListPage
      title="Plugins"
      subtitle="Portable packages that provide skills and MCP servers"
    >
      <Panel>
        <Panel.Body>
          <div style={{ maxWidth: 360 }}>
            <Select
              label="Project scope"
              data={projectOptions}
              value={projectId}
              onChange={(value) => setProjectId(value ?? "")}
            />
          </div>
        </Panel.Body>
      </Panel>

      {error ? (
        <ErrorState
          title="Could not load plugins"
          message={error.message}
          onRetry={() => void refetch()}
        />
      ) : (plugins ?? []).length === 0 ? (
        <GuidedEmptyState
          icon={RiPlugLine}
          title="No plugins found"
          description="Add a plugin under .agents/plugins in this project or in your user plugins directory."
          helpId="plugins.overview"
        />
      ) : (
        <DataTable<PluginInfo>
          rowKey={(plugin) => `${plugin.scope}:${plugin.project_id ?? ""}:${plugin.name}`}
          rows={plugins ?? []}
          columns={[
            {
              key: "name",
              header: "Plugin",
              render: (plugin) => (
                <div>
                  <strong>{plugin.name}</strong>
                  <div>{plugin.version || "unversioned"}</div>
                </div>
              ),
            },
            {
              key: "scope",
              header: "Scope",
              render: (plugin) => (
                <StatusChip
                  tone={plugin.scope === "project" ? "success" : "neutral"}
                >
                  {plugin.scope}
                </StatusChip>
              ),
            },
            {
              key: "status",
              header: "Status",
              render: (plugin) =>
                !plugin.valid ? (
                  <StatusChip tone="danger">invalid</StatusChip>
                ) : plugin.shadowed ? (
                  <StatusChip tone="warning">shadowed</StatusChip>
                ) : (
                  <StatusChip tone={plugin.enabled ? "success" : "neutral"}>
                    {plugin.enabled ? "enabled" : "disabled"}
                  </StatusChip>
                ),
            },
            {
              key: "components",
              header: "Components",
              render: (plugin) =>
                `${plugin.skills.length} skills · ${plugin.mcp_servers.length} MCP`,
            },
            {
              key: "issues",
              header: "Issues",
              render: (plugin) =>
                plugin.issues.length ? String(plugin.issues.length) : "—",
            },
            {
              key: "actions",
              header: "Actions",
              render: (plugin) => (
                <div style={{ display: "flex", gap: 4 }}>
                  <Button
                    variant="light"
                    size="compact-xs"
                    onClick={() => setDetail(plugin)}
                  >
                    Details
                  </Button>
                  {plugin.valid && !plugin.shadowed ? (
                    <Button
                      variant={plugin.enabled ? "light" : "filled"}
                      size="compact-xs"
                      onClick={() => setPending(plugin)}
                    >
                      {plugin.enabled ? "Disable" : "Enable"}
                    </Button>
                  ) : null}
                </div>
              ),
            },
          ]}
        />
      )}

      <ConfirmDialog
        opened={pending !== null}
        title={
          pending?.enabled
            ? `Disable ${pending?.name ?? ""}?`
            : `Enable ${pending?.name ?? ""}?`
        }
        description={
          pending?.enabled
            ? "Disabling removes this plugin's skills and makes its MCP servers unselectable. Stale agent references will be skipped."
            : "Only enable plugins you trust. Enabled plugins can contribute instructions and MCP servers, and MCP servers can run local commands when an agent selects them."
        }
        confirmLabel={pending?.enabled ? "Disable" : "Enable and trust"}
        danger={Boolean(pending?.enabled)}
        onConfirm={confirmToggle}
        onClose={() => setPending(null)}
      />

      <Drawer
        opened={detail !== null}
        onClose={() => setDetail(null)}
        title={detail?.name ?? "Plugin"}
        size="lg"
      >
        {detail ? <PluginDetails plugin={detail} /> : null}
      </Drawer>
    </ListPage>
  );
}

function PluginDetails({ plugin }: { plugin: PluginInfo }) {
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <strong>{plugin.name}</strong>
        <div>{plugin.description || "No description"}</div>
        <div>
          {plugin.scope} · {plugin.version || "unversioned"} ·{" "}
          {plugin.enabled ? "enabled" : "disabled"}
        </div>
      </div>
      <section>
        <h4>Skills</h4>
        {plugin.skills.length ? (
          <ul>
            {plugin.skills.map((skill) => (
              <li key={skill.name}>
                <code>{skill.name}</code> — {skill.description}
              </li>
            ))}
          </ul>
        ) : (
          <p>No skills.</p>
        )}
      </section>
      <section>
        <h4>MCP servers</h4>
        {plugin.mcp_servers.length ? (
          <ul>
            {plugin.mcp_servers.map((server) => (
              <li key={server.name}>
                <code>{server.name}</code> — {server.transport}
              </li>
            ))}
          </ul>
        ) : (
          <p>No MCP servers.</p>
        )}
      </section>
      <section>
        <h4>Validation</h4>
        {plugin.issues.length ? (
          <ul>
            {plugin.issues.map((issue, index) => (
              <li key={`${issue.component}:${index}`}>
                <strong>{issue.severity}</strong> {issue.component}:{" "}
                {issue.message}
              </li>
            ))}
          </ul>
        ) : (
          <p>No validation issues.</p>
        )}
      </section>
    </div>
  );
}
