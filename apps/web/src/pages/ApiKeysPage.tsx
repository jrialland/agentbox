import {
  Button,
  Code,
  Modal,
  MultiSelect,
  Select,
  Table,
  TextInput,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import type { ApiKey } from "../api/endpoints";
import { useApiKeys, useCreateApiKey, useRevokeApiKey } from "../api/queries";
import { useAuthStore } from "../store/auth";

const EXPIRY_OPTIONS = [
  { value: "never", label: "Never" },
  { value: "7", label: "7 days" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
];

function status(k: ApiKey): string {
  if (k.revoked_at) return "revoked";
  if (k.expires_at && new Date(k.expires_at) <= new Date()) return "expired";
  return "active";
}

export function ApiKeysPage() {
  const user = useAuthStore((s) => s.user);
  const { data: keys } = useApiKeys();
  const create = useCreateApiKey();
  const revoke = useRevokeApiKey();
  const [scopes, setScopes] = useState<string[]>([]);
  const [expiry, setExpiry] = useState<string | null>("never");
  const [created, setCreated] = useState<string | null>(null);

  async function onCreate() {
    try {
      const days = expiry === "never" ? null : Number(expiry);
      const expires_at = days
        ? new Date(Date.now() + days * 86_400_000).toISOString()
        : null;
      const res = await create.mutateAsync({ scopes, expires_at });
      setCreated(res.key);
      setScopes([]);
    } catch {
      notifications.show({ message: "Failed to create API key", color: "red" });
    }
  }

  return (
    <div>
      <h1 className="title">API keys</h1>
      <div className="box">
        <MultiSelect
          label="Scopes"
          data={[...new Set(user?.permissions ?? [])]}
          value={scopes}
          onChange={setScopes}
        />
        <Select
          label="Expires"
          data={EXPIRY_OPTIONS}
          value={expiry}
          onChange={setExpiry}
        />
        <Button mt="md" onClick={onCreate} loading={create.isPending}>
          Create key
        </Button>
      </div>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>ID</Table.Th>
            <Table.Th>Scopes</Table.Th>
            <Table.Th>Expires</Table.Th>
            <Table.Th>Status</Table.Th>
            <Table.Th>Actions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {(keys ?? []).map((k) => (
            <Table.Tr key={k.id}>
              <Table.Td>
                <Code>{k.id.slice(0, 8)}</Code>
              </Table.Td>
              <Table.Td>{k.scopes.join(", ")}</Table.Td>
              <Table.Td>
                {k.expires_at
                  ? new Date(k.expires_at).toLocaleString()
                  : "never"}
              </Table.Td>
              <Table.Td>{status(k)}</Table.Td>
              <Table.Td>
                {status(k) === "active" && (
                  <Button
                    size="xs"
                    color="red"
                    onClick={() => revoke.mutateAsync(k.id)}
                  >
                    Revoke
                  </Button>
                )}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Modal
        opened={!!created}
        onClose={() => setCreated(null)}
        title="Copy your API key"
      >
        <TextInput
          data-testid="created-key"
          value={created ?? ""}
          readOnly
          onClick={(e) => e.currentTarget.select()}
        />
        <Button
          mt="md"
          onClick={() => created && navigator.clipboard.writeText(created)}
        >
          Copy
        </Button>
      </Modal>
    </div>
  );
}
