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
  const base = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
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
