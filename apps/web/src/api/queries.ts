import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createAgent,
  createProject,
  createProvider,
  createSession,
  deleteAgent,
  deleteProject,
  deleteProvider,
  fetchAgents,
  fetchMessages,
  fetchModels,
  fetchProjects,
  fetchProviders,
  fetchSession,
  fetchSessions,
  refreshModels,
  resetAgentAvatar,
  uploadAgentAvatar,
} from "./endpoints";

export function useProjects() {
  return useQuery({ queryKey: ["projects"], queryFn: fetchProjects });
}

export function useSessions() {
  return useQuery({ queryKey: ["sessions"], queryFn: fetchSessions });
}

export function useAgents() {
  return useQuery({ queryKey: ["agents"], queryFn: fetchAgents });
}

export function useProviders() {
  return useQuery({ queryKey: ["providers"], queryFn: fetchProviders });
}

export function useModels() {
  return useQuery({ queryKey: ["models"], queryFn: fetchModels });
}

export function useMessages(sessionId: string) {
  return useQuery({
    queryKey: ["messages", sessionId],
    queryFn: () => fetchMessages(sessionId),
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createProject,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}

export function useCreateSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createSession,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteProject,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}

export function useCreateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createProvider,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers"] }),
  });
}

export function useDeleteProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteProvider,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers"] }),
  });
}

export function useRefreshModels() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: refreshModels,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["models"] }),
  });
}

export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createAgent,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}

export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteAgent,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}

export function useSession(sessionId: string) {
  return useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => fetchSession(sessionId),
    enabled: !!sessionId,
  });
}

export function useUploadAvatar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, file }: { name: string; file: File }) =>
      uploadAgentAvatar(name, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      qc.invalidateQueries({ queryKey: ["session"] });
    },
  });
}

export function useResetAvatar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => resetAgentAvatar(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      qc.invalidateQueries({ queryKey: ["session"] });
    },
  });
}
