export type PluginMcpBindingDraft = {
  plugin: string;
  server: string;
  project_id: string | null;
  id: string;
};

export function fromPluginBinding(
  binding: Record<string, unknown>,
): PluginMcpBindingDraft | null {
  const plugin = String(binding.plugin ?? "").trim();
  const server = String(binding.server ?? "").trim();
  if (!plugin || !server) return null;
  return {
    plugin,
    server,
    project_id: binding.project_id ? String(binding.project_id) : null,
    id: String(binding.id ?? `${plugin}:${server}`),
  };
}

export function toPluginBinding(
  draft: PluginMcpBindingDraft,
): Record<string, unknown> {
  return {
    plugin: draft.plugin,
    server: draft.server,
    project_id: draft.project_id,
    id: draft.id || `${draft.plugin}:${draft.server}`,
  };
}
