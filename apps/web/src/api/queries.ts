import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createAgent,
  createPermission,
  createProject,
  createProvider,
  createRole,
  createSession,
  createUser,
  deleteAgent,
  deletePermission,
  deleteProject,
  deleteProvider,
  deleteRole,
  deleteUser,
  fetchAgents,
  fetchMessages,
  fetchModels,
  fetchPermissions,
  fetchProjects,
  fetchProviders,
  fetchRolePermissions,
  fetchRoles,
  fetchSession,
  fetchSessions,
  fetchUserRoles,
  fetchUsers,
  refreshModels,
  resetAgentAvatar,
  setRolePermissions,
  setUserRoles,
  updatePermission,
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
