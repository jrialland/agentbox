import { API_URL } from "../config";
import { useAuthStore } from "../store/auth";
import { api } from "./client";
import type { components } from "./schema";

export type Project = components["schemas"]["Project"];
export type Session = components["schemas"]["SessionRow"];
export type Agent = components["schemas"]["AgentSpec"];
export type Provider = components["schemas"]["ProviderRead"];
export type Model = components["schemas"]["Model"];

export async function fetchProjects(): Promise<Project[]> {
  const { data } = await api.GET("/projects");
  return data ?? [];
}

export async function createProject(body: { name: string; path: string }): Promise<Project> {
  const { data, error } = await api.POST("/projects", { body });
  if (error) throw new Error("Failed to create project");
  return data as Project;
}

export async function deleteProject(id: string): Promise<void> {
  await api.DELETE("/projects/{pid}", { params: { path: { pid: id } } });
}

export async function fetchSessions(): Promise<Session[]> {
  const { data } = await api.GET("/sessions");
  return data ?? [];
}

export async function createSession(body: {
  project_id: string;
  agent_id: string;
}): Promise<Session> {
  const { data, error } = await api.POST("/sessions", { body });
  if (error) throw new Error("Failed to create session");
  return data as Session;
}

export async function fetchAgents(): Promise<Agent[]> {
  const { data } = await api.GET("/agents");
  return data ?? [];
}

export type Message = components["schemas"]["MessageRead"];

export async function fetchMessages(sid: string): Promise<Message[]> {
  const { data } = await api.GET("/sessions/{sid}/messages", {
    params: { path: { sid } },
  });
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
  if (!r.ok) throw new Error("upload failed");
  return r.json();
}

export async function fetchProviders(): Promise<Provider[]> {
  const { data } = await api.GET("/providers");
  return data ?? [];
}

export async function createProvider(body: {
  name: string;
  kind: string;
  base_url?: string;
  api_key?: string;
  models_url?: string;
}): Promise<Provider> {
  const { data, error } = await api.POST("/providers", { body });
  if (error) throw new Error("Failed to create provider");
  return data as Provider;
}

export async function deleteProvider(id: string): Promise<void> {
  await api.DELETE("/providers/{pid}", { params: { path: { pid: id } } });
}

export async function refreshModels(id: string): Promise<Model[]> {
  const { data } = await api.POST("/providers/{pid}/models/refresh", {
    params: { path: { pid: id } },
  });
  return data ?? [];
}

export async function fetchModels(): Promise<Model[]> {
  const { data } = await api.GET("/models");
  return data ?? [];
}

export async function createAgent(body: {
  name: string;
  description: string;
  instructions: string;
  model: string;
  tool_bindings: Record<string, unknown>[];
  mode_definitions: Record<string, unknown>[];
  sub_agent_ids: string[];
}): Promise<Agent> {
  const { data, error } = await api.POST("/agents", { body });
  if (error) throw new Error("Failed to create agent");
  return data as Agent;
}

export async function deleteAgent(name: string): Promise<void> {
  await api.DELETE("/agents/{name}", { params: { path: { name } } });
}

export type SessionDetail = components["schemas"]["SessionDetail"];

export async function fetchSession(sid: string): Promise<SessionDetail> {
  const { data, error } = await api.GET("/sessions/{sid}", {
    params: { path: { sid } },
  });
  if (error) throw new Error("Failed to fetch session");
  return data as SessionDetail;
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
  if (!r.ok) throw new Error("avatar upload failed");
}

export async function resetAgentAvatar(name: string): Promise<void> {
  const token = useAuthStore.getState().token;
  const r = await fetch(`${API_URL}/agents/${encodeURIComponent(name)}/avatar`, {
    method: "DELETE",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!r.ok) throw new Error("avatar reset failed");
}

export type Permission = components["schemas"]["PermissionRead"];
export type Role = components["schemas"]["RoleRead"];
export type User = components["schemas"]["UserRead"];

export async function fetchPermissions(): Promise<Permission[]> {
  const { data } = await api.GET("/permissions");
  return data ?? [];
}

export async function createPermission(body: {
  name: string;
  description?: string;
}): Promise<Permission> {
  const { data, error } = await api.POST("/permissions", { body });
  if (error) throw new Error("Failed to create permission");
  return data as Permission;
}

export async function updatePermission(
  pid: string,
  body: { name?: string; description?: string },
): Promise<Permission> {
  const { data, error } = await api.PUT("/permissions/{pid}", {
    params: { path: { pid } },
    body,
  });
  if (error) throw new Error("Failed to update permission");
  return data as Permission;
}

export async function deletePermission(pid: string): Promise<void> {
  await api.DELETE("/permissions/{pid}", { params: { path: { pid } } });
}

export async function fetchRoles(): Promise<Role[]> {
  const { data } = await api.GET("/roles");
  return data ?? [];
}

export async function createRole(body: {
  name: string;
  description?: string;
}): Promise<Role> {
  const { data, error } = await api.POST("/roles", { body });
  if (error) throw new Error("Failed to create role");
  return data as Role;
}

export async function deleteRole(rid: string): Promise<void> {
  await api.DELETE("/roles/{rid}", { params: { path: { rid } } });
}

export async function updateRole(
  rid: string,
  body: { name?: string; description?: string },
): Promise<Role> {
  const { data, error } = await api.PUT("/roles/{rid}", {
    params: { path: { rid } },
    body,
  });
  if (error) throw new Error("Failed to update role");
  return data as Role;
}

export async function fetchRolePermissions(rid: string): Promise<Permission[]> {
  const { data } = await api.GET("/roles/{rid}/permissions", {
    params: { path: { rid } },
  });
  return data ?? [];
}

export async function setRolePermissions(
  rid: string,
  permissionIds: string[],
): Promise<Permission[]> {
  const { data, error } = await api.PUT("/roles/{rid}/permissions", {
    params: { path: { rid } },
    body: { permission_ids: permissionIds },
  });
  if (error) throw new Error("Failed to set role permissions");
  return data ?? [];
}

export async function fetchUsers(): Promise<User[]> {
  const { data } = await api.GET("/users");
  return data ?? [];
}

export async function createUser(body: {
  username: string;
  email: string;
  password: string;
}): Promise<User> {
  const { data, error } = await api.POST("/users", { body });
  if (error) throw new Error("Failed to create user");
  return data as User;
}

export async function updateUser(
  uid: string,
  body: { email?: string; is_active?: boolean; password?: string },
): Promise<User> {
  const { data, error } = await api.PUT("/users/{uid}", {
    params: { path: { uid } },
    body,
  });
  if (error) throw new Error("Failed to update user");
  return data as User;
}

export async function deleteUser(uid: string): Promise<void> {
  await api.DELETE("/users/{uid}", { params: { path: { uid } } });
}

export async function fetchUserRoles(uid: string): Promise<Role[]> {
  const { data } = await api.GET("/users/{uid}/roles", {
    params: { path: { uid } },
  });
  return data ?? [];
}

export async function setUserRoles(uid: string, roleIds: string[]): Promise<Role[]> {
  const { data, error } = await api.PUT("/users/{uid}/roles", {
    params: { path: { uid } },
    body: { role_ids: roleIds },
  });
  if (error) throw new Error("Failed to set user roles");
  return data ?? [];
}

export type ApiKey = components["schemas"]["ApiKeyRead"];
export type ApiKeyCreated = components["schemas"]["ApiKeyCreated"];

export async function fetchApiKeys(): Promise<ApiKey[]> {
  const { data } = await api.GET("/api-keys");
  return data ?? [];
}

export async function createApiKey(body: {
  scopes: string[];
  expires_at?: string | null;
}): Promise<ApiKeyCreated> {
  const { data, error } = await api.POST("/api-keys", { body });
  if (error) throw new Error("Failed to create API key");
  return data as ApiKeyCreated;
}

export async function revokeApiKey(id: string): Promise<void> {
  await api.DELETE("/api-keys/{kid}", { params: { path: { kid: id } } });
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
  const { data, error } = await api.PUT("/providers/{pid}", {
    params: { path: { pid } },
    body,
  });
  if (error) throw new Error("Failed to update provider");
  return data as Provider;
}

export async function createModel(body: {
  provider_id: string;
  name: string;
}): Promise<Model> {
  const { data, error } = await api.POST("/models", { body });
  if (error) throw new Error("Failed to create model");
  return data as Model;
}

export async function deleteModel(mid: string): Promise<void> {
  await api.DELETE("/models/{mid}", { params: { path: { mid } } });
}

export async function deleteSession(sid: string): Promise<void> {
  await api.DELETE("/sessions/{sid}", { params: { path: { sid } } });
}

export type AgentCard = Record<string, unknown>;

export async function fetchAgentCard(name: string): Promise<AgentCard | null> {
  const { data, response } = await api.GET("/agents/{name}/card", {
    params: { path: { name } },
  });
  if (response.status === 404) return null;
  return (data as AgentCard) ?? null;
}

export async function setAgentCard(
  name: string,
  card: AgentCard,
): Promise<AgentCard> {
  const { data, error } = await api.PUT("/agents/{name}/card", {
    params: { path: { name } },
    body: card as never,
  });
  if (error) throw new Error("Failed to save agent card");
  return data as AgentCard;
}

export async function deleteAgentCard(name: string): Promise<void> {
  await api.DELETE("/agents/{name}/card", { params: { path: { name } } });
}

export type SkillInfo = { name: string; description: string; scope: string };
export type SkillDetail = SkillInfo & { body: string };

export async function fetchSkills(projectId?: string): Promise<SkillInfo[]> {
  const { data } = await api.GET("/skills", {
    params: { query: projectId ? { project_id: projectId } : {} },
  });
  return (data as SkillInfo[]) ?? [];
}

export async function fetchSkill(
  name: string,
  projectId?: string,
): Promise<SkillDetail> {
  const { data, error } = await api.GET("/skills/{name}", {
    params: { path: { name }, query: projectId ? { project_id: projectId } : {} },
  });
  if (error) throw new Error("Failed to fetch skill");
  return data as SkillDetail;
}

export async function saveSkill(
  name: string,
  body: { description: string; body: string },
): Promise<void> {
  const { error } = await api.PUT("/skills/{name}", {
    params: { path: { name } },
    body,
  });
  if (error) throw new Error("Failed to save skill");
}

export async function deleteSkill(name: string): Promise<void> {
  await api.DELETE("/skills/{name}", { params: { path: { name } } });
}

export async function fetchSessionFiles(
  sid: string,
  q: string,
): Promise<string[]> {
  const { data } = await api.GET("/sessions/{sid}/files", {
    params: { path: { sid }, query: { q } },
  });
  return (data as { files?: string[] })?.files ?? [];
}
