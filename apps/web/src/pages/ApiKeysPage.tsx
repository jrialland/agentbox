import { notifications } from "@mantine/notifications";
import { RiDeleteBin6Line } from "@remixicon/react";
import { useEffect, useRef, useState } from "react";

import type { ApiKey } from "../api/endpoints";
import { useApiKeys, useCreateApiKey, useRevokeApiKey } from "../api/queries";
import { DataTable } from "../design-system/data/DataTable";
import { FormField } from "../design-system/forms/FormField";
import { Select } from "../design-system/forms/Select";
import { TextInput } from "../design-system/forms/TextInput";
import { IconButton } from "../design-system/icons/IconButton";
import { Modal } from "../design-system/overlays/Modal";
import { ListPage } from "../design-system/patterns/ListPage";
import { Badge } from "../design-system/primitives/Badge";
import { Button } from "../design-system/primitives/Button";
import { CopyButton } from "../design-system/primitives/CopyButton";
import { Panel } from "../design-system/primitives/Panel";
import { StatusChip } from "../design-system/primitives/StatusChip";
import { HelpTip } from "../help/HelpTip";
import { useAuthStore } from "../store/auth";
import { ScopePicker } from "./api-keys/ScopePicker";
import styles from "./api-keys.module.css";

const EXPIRY_OPTIONS = [
  { value: "never", label: "Never" },
  { value: "7", label: "7 days" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
];

function status(key: ApiKey): "active" | "expired" | "revoked" {
  if (key.revoked_at) return "revoked";
  if (key.expires_at && new Date(key.expires_at) <= new Date()) return "expired";
  return "active";
}

function statusTone(value: "active" | "expired" | "revoked") {
  if (value === "active") return "success";
  if (value === "expired") return "warning";
  return "danger";
}

export function ApiKeysPage() {
  const user = useAuthStore((state) => state.user);
  const { data: keys } = useApiKeys();
  const create = useCreateApiKey();
  const revoke = useRevokeApiKey();
  const [scopes, setScopes] = useState<string[]>([]);
  const [expiry, setExpiry] = useState<string | null>("never");
  const [created, setCreated] = useState<string | null>(null);
  const createdRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (created) createdRef.current?.select();
  }, [created]);

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
    <ListPage
      title="API keys"
      subtitle="Scoped credentials for the API and A2A"
    >
      <Panel>
        <Panel.Header>Create key</Panel.Header>
        <Panel.Body>
          <div className={styles.form}>
            <FormField
              label="Scopes"
              description="Select the permissions this key may use."
              help={<HelpTip id="api.scopes" />}
            >
              <ScopePicker
                available={[...new Set(user?.permissions ?? [])]}
                value={scopes}
                onChange={setScopes}
              />
            </FormField>
            <FormField label="Expires">
              <Select
                data={EXPIRY_OPTIONS}
                value={expiry}
                onChange={setExpiry}
              />
            </FormField>
            <Button onClick={onCreate} loading={create.isPending}>
              Create key
            </Button>
          </div>
        </Panel.Body>
      </Panel>

      <DataTable<ApiKey>
        rowKey={(key) => key.id}
        rows={keys ?? []}
        columns={[
          {
            key: "id",
            header: "ID",
            render: (key) => <code>{key.id.slice(0, 8)}</code>,
          },
          {
            key: "scopes",
            header: "Scopes",
            render: (key) => (
              <div className={styles.scopes}>
                {key.scopes.length === 0 ? (
                  <span className={styles.muted}>no scopes</span>
                ) : (
                  key.scopes.map((scope) => (
                    <Badge key={scope} tone="info">
                      {scope}
                    </Badge>
                  ))
                )}
              </div>
            ),
          },
          {
            key: "expires",
            header: "Expires",
            render: (key) =>
              key.expires_at
                ? new Date(key.expires_at).toLocaleString()
                : "never",
          },
          {
            key: "status",
            header: "Status",
            render: (key) => {
              const value = status(key);
              return <StatusChip tone={statusTone(value)}>{value}</StatusChip>;
            },
          },
          {
            key: "actions",
            header: "Actions",
            render: (key) =>
              status(key) === "active" ? (
                <IconButton
                  label="Revoke"
                  icon={RiDeleteBin6Line}
                  size={16}
                  color="red"
                  onClick={() => revoke.mutateAsync(key.id)}
                />
              ) : null,
          },
        ]}
      />

      <Modal
        opened={!!created}
        onClose={() => setCreated(null)}
        title="Copy your API key"
      >
        <TextInput
          ref={createdRef}
          data-testid="created-key"
          value={created ?? ""}
          readOnly
          onClick={(e) => e.currentTarget.select()}
        />
        <div className={styles.modalActions}>
          <CopyButton value={created ?? ""} label="Copy" />
        </div>
      </Modal>
    </ListPage>
  );
}

