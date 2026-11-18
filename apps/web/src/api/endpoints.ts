import { api } from "./client";
import type { components } from "./schema";

export type Project = components["schemas"]["Project"];
export type Session = components["schemas"]["SessionRow"];
export type Agent = components["schemas"]["AgentSpec"];

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
