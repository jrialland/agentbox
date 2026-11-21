export const SCOPE_HELP: Record<string, string> = {
  "agents:create": "Create and update agents.",
  "agents:read": "View agents and their A2A cards.",
  "agents:delete": "Delete agents.",
  "providers:create": "Create and update providers.",
  "providers:read": "View providers.",
  "providers:delete": "Delete providers.",
  "providers:list-models": "Fetch the provider model list.",
  "projects:create": "Create and update projects.",
  "projects:read": "View projects.",
  "projects:delete": "Delete projects.",
  "sessions:create": "Create sessions and send messages.",
  "sessions:read": "View sessions, messages, and attachments.",
  "users:manage": "Manage users.",
  "roles:manage": "Manage roles and permissions.",
  "api_keys:manage": "Create and revoke API keys.",
};

export const RECOMMENDED_SCOPES = ["providers:read", "sessions:read"];

export function describeScope(scope: string): string {
  return SCOPE_HELP[scope] ?? scope;
}

