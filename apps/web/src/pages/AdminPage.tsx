import { Table, Tabs } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import type { Permission, Role, User } from "../api/endpoints";
import { InlineError } from "../design-system/forms/InlineError";
import { MultiSelect } from "../design-system/forms/MultiSelect";
import { PasswordInput } from "../design-system/forms/PasswordInput";
import { Switch } from "../design-system/forms/Switch";
import { Textarea } from "../design-system/forms/Textarea";
import { TextInput } from "../design-system/forms/TextInput";
import { ConfirmDialog } from "../design-system/overlays/ConfirmDialog";
import { Modal } from "../design-system/overlays/Modal";
import { AdminTablePage } from "../design-system/patterns/AdminTablePage";
import { Button } from "../design-system/primitives/Button";
import { Panel } from "../design-system/primitives/Panel";
import {
  useCreatePermission,
  useCreateRole,
  useCreateUser,
  useDeletePermission,
  useDeleteRole,
  useDeleteUser,
  usePermissions,
  useRolePermissions,
  useRoles,
  useSetRolePermissions,
  useSetUserRoles,
  useUpdatePermission,
  useUpdateRole,
  useUpdateUser,
  useUserRoles,
  useUsers,
} from "../api/queries";
import { requiredText } from "../lib/validation";

export function AdminPage() {
  return (
    <AdminTablePage title="Admin" subtitle="Access control">
      <Tabs defaultValue="permissions">
        <Tabs.List>
          <Tabs.Tab value="permissions">Permissions</Tabs.Tab>
          <Tabs.Tab value="roles">Roles</Tabs.Tab>
          <Tabs.Tab value="users">Users</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="permissions" pt="md">
          <PermissionsTab />
        </Tabs.Panel>
        <Tabs.Panel value="roles" pt="md">
          <RolesTab />
        </Tabs.Panel>
        <Tabs.Panel value="users" pt="md">
          <UsersTab />
        </Tabs.Panel>
      </Tabs>
    </AdminTablePage>
  );
}

function PermissionsTab() {
  const { data } = usePermissions();
  const create = useCreatePermission();
  const update = useUpdatePermission();
  const del = useDeletePermission();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [editing, setEditing] = useState<Permission | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const [permissionToDelete, setPermissionToDelete] =
    useState<Permission | null>(null);

  async function onCreate() {
    const nameError = requiredText(name, "Name");
    if (nameError) {
      setCreateError(nameError);
      return;
    }
    setCreateError(null);
    try {
      await create.mutateAsync({ name, description });
      setName("");
      setDescription("");
    } catch {
      notifications.show({ message: "Failed to create permission", color: "red" });
    }
  }

  function openEdit(p: Permission) {
    setEditing(p);
    setEditName(p.name);
    setEditDescription(p.description ?? "");
    setEditError(null);
  }

  async function onSaveEdit() {
    if (!editing) return;
    const nameError = requiredText(editName, "Name");
    if (nameError) {
      setEditError(nameError);
      return;
    }
    setEditError(null);
    try {
      await update.mutateAsync({
        pid: editing.id,
        body: { name: editName, description: editDescription },
      });
      setEditing(null);
    } catch {
      notifications.show({ message: "Failed to update permission", color: "red" });
    }
  }

  return (
    <div>
      <Panel>
        <Panel.Header>Create permission</Panel.Header>
        <Panel.Body>
          <TextInput
            label="Permission name"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
          />
          <Textarea
            label="Description"
            value={description}
            onChange={(e) => setDescription(e.currentTarget.value)}
          />
          {createError && <InlineError>{createError}</InlineError>}
          <Button mt="md" onClick={onCreate} loading={create.isPending}>
            Create permission
          </Button>
        </Panel.Body>
      </Panel>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Name</Table.Th>
            <Table.Th>Description</Table.Th>
            <Table.Th>Actions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {(data ?? []).map((p) => (
            <Table.Tr key={p.id}>
              <Table.Td>{p.name}</Table.Td>
              <Table.Td>{p.description}</Table.Td>
              <Table.Td>
                <Button size="xs" onClick={() => openEdit(p)}>
                  Edit
                </Button>{" "}
                <Button size="xs" color="red" onClick={() => setPermissionToDelete(p)}>
                  Delete
                </Button>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Modal opened={!!editing} onClose={() => setEditing(null)} title="Edit permission">
        <TextInput
          label="Name"
          value={editName}
          onChange={(e) => setEditName(e.currentTarget.value)}
        />
        <Textarea
          label="Description"
          value={editDescription}
          onChange={(e) => setEditDescription(e.currentTarget.value)}
        />
        {editError && <InlineError>{editError}</InlineError>}
        <Button mt="md" onClick={onSaveEdit}>
          Save
        </Button>
      </Modal>
      <ConfirmDialog
        opened={permissionToDelete !== null}
        title="Delete permission?"
        description={`Delete "${permissionToDelete?.name ?? ""}" permanently? This cannot be undone.`}
        requireText={permissionToDelete?.name}
        confirmLabel="Delete"
        danger
        onConfirm={async () => {
          if (!permissionToDelete) return;
          await del.mutateAsync(permissionToDelete.id);
          setPermissionToDelete(null);
        }}
        onClose={() => setPermissionToDelete(null)}
      />
    </div>
  );
}

function RolesTab() {
  const { data: roles } = useRoles();
  const { data: permissions } = usePermissions();
  const create = useCreateRole();
  const del = useDeleteRole();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [permRole, setPermRole] = useState<Role | null>(null);
  const [editRole, setEditRole] = useState<Role | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [roleToDelete, setRoleToDelete] = useState<Role | null>(null);

  async function onCreate() {
    const nameError = requiredText(name, "Name");
    if (nameError) {
      setCreateError(nameError);
      return;
    }
    setCreateError(null);
    try {
      await create.mutateAsync({ name, description });
      setName("");
      setDescription("");
    } catch {
      notifications.show({ message: "Failed to create role", color: "red" });
    }
  }

  return (
    <div>
      <Panel>
        <Panel.Header>Create role</Panel.Header>
        <Panel.Body>
          <TextInput
            label="Role name"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
          />
          <Textarea
            label="Description"
            value={description}
            onChange={(e) => setDescription(e.currentTarget.value)}
          />
          {createError && <InlineError>{createError}</InlineError>}
          <Button mt="md" onClick={onCreate} loading={create.isPending}>
            Create role
          </Button>
        </Panel.Body>
      </Panel>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Name</Table.Th>
            <Table.Th>Description</Table.Th>
            <Table.Th>Actions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {(roles ?? []).map((r) => (
            <Table.Tr key={r.id}>
              <Table.Td>{r.name}</Table.Td>
              <Table.Td>{r.description}</Table.Td>
              <Table.Td>
                <Button size="xs" onClick={() => setEditRole(r)}>
                  Edit
                </Button>{" "}
                <Button size="xs" onClick={() => setPermRole(r)}>
                  Permissions
                </Button>{" "}
                <Button size="xs" color="red" onClick={() => setRoleToDelete(r)}>
                  Delete
                </Button>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {editRole && <RoleEditModal role={editRole} onClose={() => setEditRole(null)} />}
      {permRole && (
        <RolePermissionsModal
          role={permRole}
          permissions={permissions ?? []}
          onClose={() => setPermRole(null)}
        />
      )}
      <ConfirmDialog
        opened={roleToDelete !== null}
        title="Delete role?"
        description={`Delete "${roleToDelete?.name ?? ""}" permanently? This cannot be undone.`}
        requireText={roleToDelete?.name}
        confirmLabel="Delete"
        danger
        onConfirm={async () => {
          if (!roleToDelete) return;
          await del.mutateAsync(roleToDelete.id);
          setRoleToDelete(null);
        }}
        onClose={() => setRoleToDelete(null)}
      />
    </div>
  );
}

function RoleEditModal({ role, onClose }: { role: Role; onClose: () => void }) {
  const update = useUpdateRole();
  const [name, setName] = useState(role.name);
  const [description, setDescription] = useState(role.description ?? "");
  const [error, setError] = useState<string | null>(null);
  async function onSave() {
    const nameError = requiredText(name, "Name");
    if (nameError) {
      setError(nameError);
      return;
    }
    setError(null);
    await update.mutateAsync({ rid: role.id, body: { name, description } });
    onClose();
  }
  return (
    <Modal opened onClose={onClose} title="Edit role">
      <TextInput
        label="Name"
        value={name}
        onChange={(e) => setName(e.currentTarget.value)}
      />
      <Textarea
        label="Description"
        value={description}
        onChange={(e) => setDescription(e.currentTarget.value)}
      />
      {error && <InlineError>{error}</InlineError>}
      <Button mt="md" onClick={onSave}>
        Save
      </Button>
    </Modal>
  );
}

function RolePermissionsModal({
  role,
  permissions,
  onClose,
}: {
  role: Role;
  permissions: Permission[];
  onClose: () => void;
}) {
  const { data: current } = useRolePermissions(role.id);
  const save = useSetRolePermissions();
  const [selected, setSelected] = useState<string[] | null>(null);
  const value = selected ?? (current ?? []).map((p) => p.id);
  async function onSave() {
    await save.mutateAsync({ rid: role.id, ids: value });
    onClose();
  }
  return (
    <Modal opened onClose={onClose} title={`Permissions for ${role.name}`}>
      <MultiSelect
        label="Permissions"
        data={permissions.map((p) => ({ value: p.id, label: p.name }))}
        value={value}
        onChange={setSelected}
      />
      <Button mt="md" onClick={onSave}>
        Save
      </Button>
    </Modal>
  );
}

function UsersTab() {
  const { data: users } = useUsers();
  const { data: roles } = useRoles();
  const create = useCreateUser();
  const del = useDeleteUser();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [editUser, setEditUser] = useState<User | null>(null);
  const [rolesUser, setRolesUser] = useState<User | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [userToDelete, setUserToDelete] = useState<User | null>(null);

  async function onCreate() {
    const next =
      requiredText(username, "Username") ??
      requiredText(email, "Email") ??
      requiredText(password, "Password");
    if (next) {
      setCreateError(next);
      return;
    }
    setCreateError(null);
    try {
      await create.mutateAsync({ username, email, password });
      setUsername("");
      setEmail("");
      setPassword("");
    } catch {
      notifications.show({ message: "Failed to create user", color: "red" });
    }
  }

  return (
    <div>
      <Panel>
        <Panel.Header>Create user</Panel.Header>
        <Panel.Body>
          <TextInput
            label="Username"
            value={username}
            onChange={(e) => setUsername(e.currentTarget.value)}
          />
          <TextInput
            label="Email"
            value={email}
            onChange={(e) => setEmail(e.currentTarget.value)}
          />
          <PasswordInput
            label="Password"
            value={password}
            onChange={(e) => setPassword(e.currentTarget.value)}
          />
          {createError && <InlineError>{createError}</InlineError>}
          <Button mt="md" onClick={onCreate} loading={create.isPending}>
            Create user
          </Button>
        </Panel.Body>
      </Panel>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Username</Table.Th>
            <Table.Th>Email</Table.Th>
            <Table.Th>Active</Table.Th>
            <Table.Th>Actions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {(users ?? []).map((u) => (
            <Table.Tr key={u.id}>
              <Table.Td>{u.username}</Table.Td>
              <Table.Td>{u.email}</Table.Td>
              <Table.Td>{u.is_active ? "yes" : "no"}</Table.Td>
              <Table.Td>
                <Button size="xs" onClick={() => setEditUser(u)}>
                  Edit
                </Button>{" "}
                <Button size="xs" onClick={() => setRolesUser(u)}>
                  Roles
                </Button>{" "}
                <Button size="xs" color="red" onClick={() => setUserToDelete(u)}>
                  Delete
                </Button>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {editUser && (
        <UserEditModal user={editUser} onClose={() => setEditUser(null)} />
      )}
      {rolesUser && (
        <UserRolesModal
          user={rolesUser}
          roles={roles ?? []}
          onClose={() => setRolesUser(null)}
        />
      )}
      <ConfirmDialog
        opened={userToDelete !== null}
        title="Delete user?"
        description={`Delete "${userToDelete?.username ?? ""}" permanently? This cannot be undone.`}
        requireText={userToDelete?.username}
        confirmLabel="Delete"
        danger
        onConfirm={async () => {
          if (!userToDelete) return;
          await del.mutateAsync(userToDelete.id);
          setUserToDelete(null);
        }}
        onClose={() => setUserToDelete(null)}
      />
    </div>
  );
}

function UserEditModal({ user, onClose }: { user: User; onClose: () => void }) {
  const update = useUpdateUser();
  const [email, setEmail] = useState(user.email);
  const [isActive, setIsActive] = useState(user.is_active);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  async function onSave() {
    const emailError = requiredText(email, "Email");
    if (emailError) {
      setError(emailError);
      return;
    }
    setError(null);
    await update.mutateAsync({
      uid: user.id,
      body: { email, is_active: isActive, ...(password ? { password } : {}) },
    });
    onClose();
  }
  return (
    <Modal opened onClose={onClose} title="Edit user">
      <TextInput
        label="Email"
        value={email}
        onChange={(e) => setEmail(e.currentTarget.value)}
      />
      <Switch
        label="Active"
        checked={isActive}
        onChange={(e) => setIsActive(e.currentTarget.checked)}
      />
      <PasswordInput
        label="New password"
        value={password}
        onChange={(e) => setPassword(e.currentTarget.value)}
      />
      {error && <InlineError>{error}</InlineError>}
      <Button mt="md" onClick={onSave}>
        Save
      </Button>
    </Modal>
  );
}

function UserRolesModal({
  user,
  roles,
  onClose,
}: {
  user: User;
  roles: Role[];
  onClose: () => void;
}) {
  const { data: current } = useUserRoles(user.id);
  const save = useSetUserRoles();
  const [selected, setSelected] = useState<string[] | null>(null);
  const value = selected ?? (current ?? []).map((r) => r.id);
  async function onSave() {
    await save.mutateAsync({ uid: user.id, ids: value });
    onClose();
  }
  return (
    <Modal opened onClose={onClose} title={`Roles for ${user.username}`}>
      <MultiSelect
        label="Roles"
        data={roles.map((r) => ({ value: r.id, label: r.name }))}
        value={value}
        onChange={setSelected}
      />
      <Button mt="md" onClick={onSave}>
        Save
      </Button>
    </Modal>
  );
}
