const BUILT_INS: Record<string, string> = {
  "agents:create": "Create and update agent configurations.",
  "agents:read": "List and inspect agent configurations.",
  "agents:delete": "Delete agent configurations.",
  "providers:create": "Create and update model providers.",
  "providers:read": "List providers and their non-secret settings.",
  "providers:delete": "Delete model providers.",
  "providers:list-models": "Discover models from a provider endpoint.",
  "projects:create": "Create and update projects.",
  "projects:read": "List projects and open project workspaces.",
  "projects:delete": "Delete projects.",
  "sessions:create": "Create sessions, send messages, and rename sessions.",
  "sessions:read": "Read sessions, messages, plans, and diagnostics.",
  "users:manage": "Create and manage users.",
  "roles:manage": "Manage roles, permissions, and assignments.",
  "api_keys:manage": "Create, inspect, and revoke API keys.",
  "plugins:read": "List and inspect installed Agent Plugins.",
  "plugins:write": "Enable, disable, and trust Agent Plugins.",
};

export function describePermission(name: string, stored?: string | null): string {
  const custom = stored?.trim();
  return custom || BUILT_INS[name] || "No description";
}
