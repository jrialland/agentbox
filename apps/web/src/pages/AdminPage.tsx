import {
  Button,
  Modal,
  MultiSelect,
  Table,
  Tabs,
  Textarea,
  TextInput,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import type { Permission, Role } from "../api/endpoints";
import {
  useCreatePermission,
  useCreateRole,
  useDeletePermission,
  useDeleteRole,
  usePermissions,
  useRolePermissions,
  useRoles,
  useSetRolePermissions,
  useUpdatePermission,
  useUpdateRole,
} from "../api/queries";

export function AdminPage() {
  return (
    <div>
      <h1 className="title">Admin</h1>
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
    </div>
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

  async function onCreate() {
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
  }

  async function onSaveEdit() {
    if (!editing) return;
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
      <div className="box">
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
        <Button mt="md" onClick={onCreate} loading={create.isPending}>
          Create permission
        </Button>
      </div>
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
                <Button size="xs" color="red" onClick={() => del.mutateAsync(p.id)}>
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
        <Button mt="md" onClick={onSaveEdit}>
          Save
        </Button>
      </Modal>
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

  async function onCreate() {
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
      <div className="box">
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
        <Button mt="md" onClick={onCreate} loading={create.isPending}>
          Create role
        </Button>
      </div>
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
                <Button size="xs" color="red" onClick={() => del.mutateAsync(r.id)}>
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
    </div>
  );
}

function RoleEditModal({ role, onClose }: { role: Role; onClose: () => void }) {
  const update = useUpdateRole();
  const [name, setName] = useState(role.name);
  const [description, setDescription] = useState(role.description ?? "");
  async function onSave() {
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
  return null;
}
