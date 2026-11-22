import { API_URL } from "../config";
import { useAuthStore } from "../store/auth";
import { api } from "./client";
import { toApiError } from "./errors";
import type { components } from "./schema";

export type Project = components["schemas"]["ProjectRead"];
export type Session = components["schemas"]["SessionRow"];
export type Agent = components["schemas"]["AgentSpec"];
export type Provider = components["schemas"]["ProviderRead"];
export type Model = components["schemas"]["ModelRead"];
export type Label = components["schemas"]["LabelRead"];
export type ProviderTestResult = components["schemas"]["ProviderTestResult"];

export type ProviderTestInput = {
  kind: string;
  base_url?: string | null;
  models_url?: string | null;
  api_key?: string | null;
  provider_id?: string | null;
};

export async function fetchProjects(): Promise<Project[]> {
  const { data, error, response } = await api.GET("/projects");
  if (error || !response.ok) throw toApiError(error, "Failed to load projects", response.status);
  return data ?? [];
}

export async function createProject(body: {
  name: string;
  path: string;
  extra_roots: string[];
}): Promise<Project> {
  const { data, error, response } = await api.POST("/projects", { body });
  if (error || !response.ok) throw toApiError(error, "Failed to create project", response.status);
  return data as Project;
}

export async function updateProject(
  pid: string,
  body: { name?: string; extra_roots?: string[] },
): Promise<Project> {
  const { data, error, response } = await api.PUT("/projects/{pid}", {
    params: { path: { pid } },
    body,
  });
  if (error || !response.ok) throw toApiError(error, "Failed to update project", response.status);
  return data as Project;
}

export async function deleteProject(id: string): Promise<void> {
  const { error, response } = await api.DELETE("/projects/{pid}", {
    params: { path: { pid: id } },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to delete project", response.status);
}

export async function fetchSessions(): Promise<Session[]> {
  const { data, error, response } = await api.GET("/sessions");
  if (error || !response.ok) throw toApiError(error, "Failed to load sessions", response.status);
  return data ?? [];
}

export async function createSession(body: {
  project_id: string;
  agent_id: string;
}): Promise<Session> {
  const { data, error, response } = await api.POST("/sessions", { body });
  if (error || !response.ok) throw toApiError(error, "Failed to create session", response.status);
  return data as Session;
}

export async function renameSession(sid: string, title: string): Promise<Session> {
  const { data, error, response } = await api.PATCH("/sessions/{sid}", {
    params: { path: { sid } },
    body: { title },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to rename session", response.status);
  return data as Session;
}

export async function fetchAgents(): Promise<Agent[]> {
  const { data, error, response } = await api.GET("/agents");
  if (error || !response.ok) throw toApiError(error, "Failed to load agents", response.status);
  return data ?? [];
}

export type Message = components["schemas"]["MessageRead"];

export async function fetchMessages(sid: string): Promise<Message[]> {
  const { data, error, response } = await api.GET("/sessions/{sid}/messages", {
    params: { path: { sid } },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to load messages", response.status);
  return data ?? [];
}

export async function uploadAttachment(
  sid: string,
  file: File,
): Promise<{ id: string; media_type: string; filename: string }> {
  const base = API_URL;
  const form = new FormData();
  form.append("file", file);
  const token = useAuthStore.getState().token;
  const r = await fetch(`${base}/sessions/${sid}/attachments`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!r.ok) {
    throw toApiError(
      await r.json().catch(() => null),
      "upload failed",
      r.status,
    );
  }
  return r.json();
}

export async function fetchProviders(): Promise<Provider[]> {
  const { data, error, response } = await api.GET("/providers");
  if (error || !response.ok) throw toApiError(error, "Failed to load providers", response.status);
  return data ?? [];
}

export async function createProvider(body: {
  name: string;
  kind: string;
  base_url?: string;
  api_key?: string;
  models_url?: string;
}): Promise<Provider> {
  const { data, error, response } = await api.POST("/providers", { body });
  if (error || !response.ok) throw toApiError(error, "Failed to create provider", response.status);
  return data as Provider;
}

export async function testProvider(
  body: ProviderTestInput,
): Promise<ProviderTestResult> {
  const { data, error, response } = await api.POST("/providers/test", { body });
  if (error || !response.ok) throw toApiError(error, "Failed to test provider", response.status);
  return data as ProviderTestResult;
}

export async function deleteProvider(id: string): Promise<void> {
  const { error, response } = await api.DELETE("/providers/{pid}", {
    params: { path: { pid: id } },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to delete provider", response.status);
}

export async function refreshModels(id: string): Promise<Model[]> {
  const { data, error, response } = await api.POST("/providers/{pid}/models/refresh", {
    params: { path: { pid: id } },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to refresh models", response.status);
  return data ?? [];
}

export async function fetchModels(): Promise<Model[]> {
  const { data, error, response } = await api.GET("/models");
  if (error || !response.ok) throw toApiError(error, "Failed to load models", response.status);
  return data ?? [];
}

export async function fetchLabels(): Promise<Label[]> {
  const { data, error, response } = await api.GET("/labels");
  if (error || !response.ok) throw toApiError(error, "Failed to load labels", response.status);
  return data ?? [];
}

export async function setModelLabels(
  mid: string,
  labels: { label: string; priority: number }[],
): Promise<Model> {
  const { data, error, response } = await api.PUT("/models/{mid}/labels", {
    params: { path: { mid } },
    body: { labels },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to set labels", response.status);
  return data as Model;
}

export type PromptPreview = {
  rendered: string;
  missing: string[];
  error: { message: string; line?: number | null } | null;
  context: Record<string, string>;
  variables: string[];
};

export async function previewPrompt(body: {
  template: string;
  context: Record<string, string>;
}): Promise<PromptPreview> {
  const { data, error, response } = await api.POST("/prompts/preview", { body });
  if (error || !response.ok) throw toApiError(error, "Failed to preview prompt", response.status);
  return data as PromptPreview;
}

export async function createAgent(body: {
  name: string;
  description: string;
  instructions: string;
  model?: string;
  model_label?: string;
  tool_bindings: Record<string, unknown>[];
  plugin_mcp_bindings?: Record<string, unknown>[];
  mode_definitions: Record<string, unknown>[];
}): Promise<Agent> {
  const { data, error, response } = await api.POST("/agents", {
    body: {
      ...body,
      plugin_mcp_bindings: body.plugin_mcp_bindings ?? [],
    },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to create agent", response.status);
  return data as Agent;
}

export async function updateAgent(
  name: string,
  body: {
    name: string;
    description: string;
    instructions: string;
    model?: string;
    model_label?: string;
    tool_bindings: Record<string, unknown>[];
    plugin_mcp_bindings?: Record<string, unknown>[];
    mode_definitions: Record<string, unknown>[];
  },
): Promise<Agent> {
  const { data, error, response } = await api.PUT("/agents/{name}", {
    params: { path: { name } },
    body: {
      ...body,
      plugin_mcp_bindings: body.plugin_mcp_bindings ?? [],
    },
  });
  if (error || !response.ok)
    throw toApiError(error, "Failed to update agent", response.status);
  return data as Agent;
}

export async function deleteAgent(name: string): Promise<void> {
  const { error, response } = await api.DELETE("/agents/{name}", {
    params: { path: { name } },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to delete agent", response.status);
}

export type SessionDetail = components["schemas"]["SessionDetail"];

export async function fetchSession(sid: string): Promise<SessionDetail> {
  const { data, error, response } = await api.GET("/sessions/{sid}", {
    params: { path: { sid } },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to fetch session", response.status);
  return data as SessionDetail;
}

export type SessionLspSnapshot = {
  path: string;
  stack: string;
  state: string;
  errors: number;
  warnings: number;
  updated_at: number;
};

export type SessionLsp = {
  detected: string[];
  active: {
    stack: string;
    command: string;
    root: string;
    status: string;
    state?: string;
    documents: number;
    last_error?: string | null;
  }[];
  snapshots?: SessionLspSnapshot[];
};

export async function fetchSessionLsp(sid: string): Promise<SessionLsp> {
  const { data, error, response } = await api.GET("/sessions/{sid}/lsp", {
    params: { path: { sid } },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to load session LSP", response.status);
  return data as SessionLsp;
}

export type PlanItem = {
  id: string;
  position: number;
  content: string;
  status: string;
};

export type SessionPlan = { items: PlanItem[] };

export async function fetchSessionPlan(sid: string): Promise<SessionPlan> {
  const { data, error, response } = await api.GET("/sessions/{sid}/plan", {
    params: { path: { sid } },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to load session plan", response.status);
  return data as SessionPlan;
}

export async function uploadAgentAvatar(name: string, file: File): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  const token = useAuthStore.getState().token;
  const r = await fetch(`${API_URL}/agents/${encodeURIComponent(name)}/avatar`, {
    method: "PUT",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!r.ok) {
    throw toApiError(
      await r.json().catch(() => null),
      "avatar upload failed",
      r.status,
    );
  }
}

export async function resetAgentAvatar(name: string): Promise<void> {
  const token = useAuthStore.getState().token;
  const r = await fetch(`${API_URL}/agents/${encodeURIComponent(name)}/avatar`, {
    method: "DELETE",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!r.ok) {
    throw toApiError(
      await r.json().catch(() => null),
      "avatar reset failed",
      r.status,
    );
  }
}

export type Permission = components["schemas"]["PermissionRead"];
export type Role = components["schemas"]["RoleRead"];
export type User = components["schemas"]["UserRead"];

export async function fetchPermissions(): Promise<Permission[]> {
  const { data, error, response } = await api.GET("/permissions");
  if (error || !response.ok) throw toApiError(error, "Failed to load permissions", response.status);
  return data ?? [];
}

export async function createPermission(body: {
  name: string;
  description?: string;
}): Promise<Permission> {
  const { data, error, response } = await api.POST("/permissions", { body });
  if (error || !response.ok) throw toApiError(error, "Failed to create permission", response.status);
  return data as Permission;
}

export async function updatePermission(
  pid: string,
  body: { name?: string; description?: string },
): Promise<Permission> {
  const { data, error, response } = await api.PUT("/permissions/{pid}", {
    params: { path: { pid } },
    body,
  });
  if (error || !response.ok) throw toApiError(error, "Failed to update permission", response.status);
  return data as Permission;
}

export async function deletePermission(pid: string): Promise<void> {
  const { error, response } = await api.DELETE("/permissions/{pid}", {
    params: { path: { pid } },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to delete permission", response.status);
}

export async function fetchRoles(): Promise<Role[]> {
  const { data, error, response } = await api.GET("/roles");
  if (error || !response.ok) throw toApiError(error, "Failed to load roles", response.status);
  return data ?? [];
}

export async function createRole(body: {
  name: string;
  description?: string;
}): Promise<Role> {
  const { data, error, response } = await api.POST("/roles", { body });
  if (error || !response.ok) throw toApiError(error, "Failed to create role", response.status);
  return data as Role;
}

export async function deleteRole(rid: string): Promise<void> {
  const { error, response } = await api.DELETE("/roles/{rid}", {
    params: { path: { rid } },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to delete role", response.status);
}

export async function updateRole(
  rid: string,
  body: { name?: string; description?: string },
): Promise<Role> {
  const { data, error, response } = await api.PUT("/roles/{rid}", {
    params: { path: { rid } },
    body,
  });
  if (error || !response.ok) throw toApiError(error, "Failed to update role", response.status);
  return data as Role;
}

export async function fetchRolePermissions(rid: string): Promise<Permission[]> {
  const { data, error, response } = await api.GET("/roles/{rid}/permissions", {
    params: { path: { rid } },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to load role permissions", response.status);
  return data ?? [];
}

export async function setRolePermissions(
  rid: string,
  permissionIds: string[],
): Promise<Permission[]> {
  const { data, error, response } = await api.PUT("/roles/{rid}/permissions", {
    params: { path: { rid } },
    body: { permission_ids: permissionIds },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to set role permissions", response.status);
  return data ?? [];
}

export async function fetchUsers(): Promise<User[]> {
  const { data, error, response } = await api.GET("/users");
  if (error || !response.ok) throw toApiError(error, "Failed to load users", response.status);
  return data ?? [];
}

export async function createUser(body: {
  username: string;
  email: string;
  password: string;
}): Promise<User> {
  const { data, error, response } = await api.POST("/users", { body });
  if (error || !response.ok) throw toApiError(error, "Failed to create user", response.status);
  return data as User;
}

export async function updateUser(
  uid: string,
  body: { email?: string; is_active?: boolean; password?: string },
): Promise<User> {
  const { data, error, response } = await api.PUT("/users/{uid}", {
    params: { path: { uid } },
    body,
  });
  if (error || !response.ok) throw toApiError(error, "Failed to update user", response.status);
  return data as User;
}

export async function deleteUser(uid: string): Promise<void> {
  const { error, response } = await api.DELETE("/users/{uid}", {
    params: { path: { uid } },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to delete user", response.status);
}

export async function fetchUserRoles(uid: string): Promise<Role[]> {
  const { data, error, response } = await api.GET("/users/{uid}/roles", {
    params: { path: { uid } },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to load user roles", response.status);
  return data ?? [];
}

export async function setUserRoles(uid: string, roleIds: string[]): Promise<Role[]> {
  const { data, error, response } = await api.PUT("/users/{uid}/roles", {
    params: { path: { uid } },
    body: { role_ids: roleIds },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to set user roles", response.status);
  return data ?? [];
}

export type ApiKey = components["schemas"]["ApiKeyRead"];
export type ApiKeyCreated = components["schemas"]["ApiKeyCreated"];

export async function fetchApiKeys(): Promise<ApiKey[]> {
  const { data, error, response } = await api.GET("/api-keys");
  if (error || !response.ok) throw toApiError(error, "Failed to load API keys", response.status);
  return data ?? [];
}

export async function createApiKey(body: {
  scopes: string[];
  expires_at?: string | null;
}): Promise<ApiKeyCreated> {
  const { data, error, response } = await api.POST("/api-keys", { body });
  if (error || !response.ok) throw toApiError(error, "Failed to create API key", response.status);
  return data as ApiKeyCreated;
}

export async function revokeApiKey(id: string): Promise<void> {
  const { error, response } = await api.DELETE("/api-keys/{kid}", {
    params: { path: { kid: id } },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to revoke API key", response.status);
}

export async function updateProvider(
  pid: string,
  body: {
    name?: string;
    kind?: string;
    base_url?: string;
    api_key?: string;
    models_url?: string;
  },
): Promise<Provider> {
  const { data, error, response } = await api.PUT("/providers/{pid}", {
    params: { path: { pid } },
    body,
  });
  if (error || !response.ok) throw toApiError(error, "Failed to update provider", response.status);
  return data as Provider;
}

export async function createModel(body: {
  provider_id: string;
  name: string;
  context_window?: number;
  labels: { label: string; priority: number }[];
}): Promise<Model> {
  const { data, error, response } = await api.POST("/models", { body });
  if (error || !response.ok) throw toApiError(error, "Failed to create model", response.status);
  return data as Model;
}

export async function deleteModel(mid: string): Promise<void> {
  const { error, response } = await api.DELETE("/models/{mid}", {
    params: { path: { mid } },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to delete model", response.status);
}

export async function deleteSession(sid: string): Promise<void> {
  const { error, response } = await api.DELETE("/sessions/{sid}", {
    params: { path: { sid } },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to delete session", response.status);
}

export type AgentCard = Record<string, unknown>;

export async function fetchAgentCard(name: string): Promise<AgentCard | null> {
  const { data, error, response } = await api.GET("/agents/{name}/card", {
    params: { path: { name } },
  });
  if (response.status === 404) return null;
  if (error || !response.ok) throw toApiError(error, "Failed to load agent card", response.status);
  return (data as AgentCard) ?? null;
}

export async function setAgentCard(
  name: string,
  card: AgentCard,
): Promise<AgentCard> {
  const { data, error, response } = await api.PUT("/agents/{name}/card", {
    params: { path: { name } },
    body: card as never,
  });
  if (error || !response.ok) throw toApiError(error, "Failed to save agent card", response.status);
  return data as AgentCard;
}

export async function deleteAgentCard(name: string): Promise<void> {
  const { error, response } = await api.DELETE("/agents/{name}/card", {
    params: { path: { name } },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to delete agent card", response.status);
}

export type SkillInfo = {
  name: string;
  description: string;
  scope: string;
  plugin?: string | null;
};
export type SkillDetail = SkillInfo & { body: string };

export type PluginSkillInfo = { name: string; description: string };
export type PluginMcpInfo = { name: string; transport: string };
export type PluginIssue = {
  severity: string;
  component: string;
  message: string;
};
export type PluginInfo = {
  name: string;
  version: string;
  description: string;
  scope: string;
  project_id: string | null;
  enabled: boolean;
  valid: boolean;
  shadowed: boolean;
  author: Record<string, unknown>;
  homepage: string;
  repository: string;
  license: string;
  keywords: string[];
  skills: PluginSkillInfo[];
  mcp_servers: PluginMcpInfo[];
  issues: PluginIssue[];
};
export type PluginStateUpdate = {
  plugin_name: string;
  scope: string;
  project_id?: string | null;
  enabled: boolean;
};

export async function fetchPlugins(
  projectId?: string,
): Promise<PluginInfo[]> {
  const { data, error, response } = await api.GET("/plugins", {
    params: { query: projectId ? { project_id: projectId } : {} },
  });
  if (error || !response.ok)
    throw toApiError(error, "Failed to load plugins", response.status);
  return (data as PluginInfo[]) ?? [];
}

export async function fetchPlugin(
  scope: string,
  name: string,
  projectId?: string,
): Promise<PluginInfo> {
  const { data, error, response } = await api.GET(
    "/plugins/{scope}/{name}",
    {
      params: {
        path: { scope, name },
        query: projectId ? { project_id: projectId } : {},
      },
    },
  );
  if (error || !response.ok)
    throw toApiError(error, "Failed to load plugin", response.status);
  return data as PluginInfo;
}

export async function setPluginState(
  body: PluginStateUpdate,
): Promise<PluginInfo> {
  const { data, error, response } = await api.PUT("/plugins/state", {
    body,
  });
  if (error || !response.ok)
    throw toApiError(error, "Failed to update plugin", response.status);
  return data as PluginInfo;
}

export async function fetchSkills(projectId?: string): Promise<SkillInfo[]> {
  const { data, error, response } = await api.GET("/skills", {
    params: { query: projectId ? { project_id: projectId } : {} },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to load skills", response.status);
  return (data as SkillInfo[]) ?? [];
}

export async function fetchSkill(
  name: string,
  projectId?: string,
): Promise<SkillDetail> {
  const { data, error, response } = await api.GET("/skills/{name}", {
    params: { path: { name }, query: projectId ? { project_id: projectId } : {} },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to fetch skill", response.status);
  return data as SkillDetail;
}

export async function saveSkill(
  name: string,
  body: { description: string; body: string },
): Promise<void> {
  const { error, response } = await api.PUT("/skills/{name}", {
    params: { path: { name } },
    body,
  });
  if (error || !response.ok) throw toApiError(error, "Failed to save skill", response.status);
}

export async function deleteSkill(name: string): Promise<void> {
  const { error, response } = await api.DELETE("/skills/{name}", {
    params: { path: { name } },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to delete skill", response.status);
}

export async function fetchSessionFiles(
  sid: string,
  q: string,
): Promise<string[]> {
  const { data, error, response } = await api.GET("/sessions/{sid}/files", {
    params: { path: { sid }, query: { q } },
  });
  if (error || !response.ok) throw toApiError(error, "Failed to load session files", response.status);
  return (data as { files?: string[] })?.files ?? [];
}
