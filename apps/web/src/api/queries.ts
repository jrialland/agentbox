import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createAgent,
  createApiKey,
  createModel,
  createPermission,
  createProject,
  createProvider,
  createRole,
  createSession,
  createUser,
  deleteAgent,
  deleteAgentCard,
  deleteModel,
  deletePermission,
  deleteProject,
  deleteProvider,
  deleteRole,
  deleteSession,
  deleteSkill,
  deleteUser,
  fetchAgentCard,
  fetchAgents,
  fetchApiKeys,
  fetchLabels,
  fetchMessages,
  fetchModels,
  fetchPermissions,
  fetchProjects,
  fetchProviders,
  fetchRolePermissions,
  fetchRoles,
  fetchSkill,
  fetchSkills,
  fetchSession,
  fetchSessionFiles,
  fetchSessionLsp,
  fetchSessionPlan,
  fetchSessions,
  fetchUserRoles,
  fetchUsers,
  previewPrompt,
  refreshModels,
  resetAgentAvatar,
  saveSkill,
  revokeApiKey,
  setAgentCard,
  setModelLabels,
  setRolePermissions,
  setUserRoles,
  testProvider,
  updatePermission,
  updateProject,
  updateProvider,
  updateRole,
  updateUser,
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

export function useLabels() {
  return useQuery({ queryKey: ["labels"], queryFn: fetchLabels });
}

export function usePreviewPrompt() {
  return useMutation({ mutationFn: previewPrompt });
}

export function useSetModelLabels() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      mid: string;
      labels: { label: string; priority: number }[];
    }) => setModelLabels(input.mid, input.labels),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["models"] });
      void qc.invalidateQueries({ queryKey: ["labels"] });
    },
  });
}

export function useMessages(sessionId: string, enabled = true) {
  return useQuery({
    queryKey: ["messages", sessionId],
    queryFn: () => fetchMessages(sessionId),
    enabled: enabled && !!sessionId,
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createProject,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}

export function useUpdateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      pid: string;
      body: { name?: string; extra_roots?: string[] };
    }) => updateProject(input.pid, input.body),
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

export function useTestProvider() {
  return useMutation({ mutationFn: testProvider });
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

export function useSessionLsp(sessionId: string, enabled = true) {
  return useQuery({
    queryKey: ["session-lsp", sessionId],
    queryFn: () => fetchSessionLsp(sessionId),
    enabled: enabled && !!sessionId,
  });
}

export function useSessionPlan(sessionId: string, running = false, enabled = true) {
  return useQuery({
    queryKey: ["session-plan", sessionId],
    queryFn: () => fetchSessionPlan(sessionId),
    enabled: enabled && !!sessionId,
    refetchInterval: running ? 2000 : false,
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

export function usePermissions() {
  return useQuery({ queryKey: ["permissions"], queryFn: fetchPermissions });
}

export function useRoles() {
  return useQuery({ queryKey: ["roles"], queryFn: fetchRoles });
}

export function useUsers() {
  return useQuery({ queryKey: ["users"], queryFn: fetchUsers });
}

export function useRolePermissions(rid: string | null) {
  return useQuery({
    queryKey: ["role-permissions", rid],
    queryFn: () => fetchRolePermissions(rid as string),
    enabled: !!rid,
  });
}

export function useUserRoles(uid: string | null) {
  return useQuery({
    queryKey: ["user-roles", uid],
    queryFn: () => fetchUserRoles(uid as string),
    enabled: !!uid,
  });
}

export function useCreatePermission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createPermission,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["permissions"] }),
  });
}

export function useUpdatePermission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      pid,
      body,
    }: {
      pid: string;
      body: { name?: string; description?: string };
    }) => updatePermission(pid, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["permissions"] }),
  });
}

export function useDeletePermission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deletePermission,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["permissions"] }),
  });
}

export function useCreateRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createRole,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["roles"] }),
  });
}

export function useUpdateRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      rid,
      body,
    }: {
      rid: string;
      body: { name?: string; description?: string };
    }) => updateRole(rid, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["roles"] }),
  });
}

export function useDeleteRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteRole,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["roles"] }),
  });
}

export function useSetRolePermissions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ rid, ids }: { rid: string; ids: string[] }) =>
      setRolePermissions(rid, ids),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ["role-permissions", v.rid] });
      qc.invalidateQueries({ queryKey: ["roles"] });
    },
  });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createUser,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      uid,
      body,
    }: {
      uid: string;
      body: { email?: string; is_active?: boolean; password?: string };
    }) => updateUser(uid, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteUser,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useUpdateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      pid,
      body,
    }: {
      pid: string;
      body: Parameters<typeof updateProvider>[1];
    }) => updateProvider(pid, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers"] }),
  });
}

export function useCreateModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createModel,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["models"] }),
  });
}

export function useDeleteModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteModel,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["models"] }),
  });
}

export function useDeleteSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteSession,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
}

export function useAgentCard(name: string | null) {
  return useQuery({
    queryKey: ["agent-card", name],
    queryFn: () => fetchAgentCard(name as string),
    enabled: !!name,
  });
}

export function useSetAgentCard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      name,
      card,
    }: {
      name: string;
      card: Record<string, unknown>;
    }) => setAgentCard(name, card),
    onSuccess: (_d, v) =>
      qc.invalidateQueries({ queryKey: ["agent-card", v.name] }),
  });
}

export function useDeleteAgentCard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteAgentCard,
    onSuccess: (_d, name) =>
      qc.invalidateQueries({ queryKey: ["agent-card", name] }),
  });
}

export function useSetUserRoles() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uid, ids }: { uid: string; ids: string[] }) =>
      setUserRoles(uid, ids),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ["user-roles", v.uid] });
      qc.invalidateQueries({ queryKey: ["users"] });
    },
  });
}

export function useApiKeys() {
  return useQuery({ queryKey: ["api-keys"], queryFn: fetchApiKeys });
}

export function useCreateApiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createApiKey,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["api-keys"] }),
  });
}

export function useRevokeApiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: revokeApiKey,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["api-keys"] }),
  });
}


export function useSkills() {
  return useQuery({ queryKey: ["skills"], queryFn: () => fetchSkills() });
}

export function useSaveSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      name,
      body,
    }: {
      name: string;
      body: { description: string; body: string };
    }) => saveSkill(name, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["skills"] }),
  });
}

export function useDeleteSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteSkill,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["skills"] }),
  });
}


export function useSessionFiles(sid: string, q: string) {
  return useQuery({
    queryKey: ["session-files", sid, q],
    queryFn: () => fetchSessionFiles(sid, q),
    enabled: q.length > 0,
    staleTime: 10_000,
  });
}

