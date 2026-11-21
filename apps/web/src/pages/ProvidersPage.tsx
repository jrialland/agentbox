import { notifications } from "@mantine/notifications";
import {
  RiAddLine,
  RiDeleteBin6Line,
  RiRefreshLine,
  RiSettings3Line,
} from "@remixicon/react";
import { useEffect, useState } from "react";

import type { Model, Provider } from "../api/endpoints";
import {
  useCreateModel,
  useCreateProvider,
  useDeleteModel,
  useDeleteProvider,
  useLabels,
  useModels,
  useProviders,
  useRefreshModels,
  useSetModelLabels,
  useUpdateProvider,
} from "../api/queries";
import { DataTable } from "../design-system/data/DataTable";
import { FormField } from "../design-system/forms/FormField";
import { NumberInput } from "../design-system/forms/NumberInput";
import { Select } from "../design-system/forms/Select";
import { TextInput } from "../design-system/forms/TextInput";
import { IconButton } from "../design-system/icons/IconButton";
import { ConfirmDialog } from "../design-system/overlays/ConfirmDialog";
import { Drawer } from "../design-system/overlays/Drawer";
import { Modal } from "../design-system/overlays/Modal";
import { GuidedEmptyState } from "../design-system/patterns/GuidedEmptyState";
import { ListPage } from "../design-system/patterns/ListPage";
import { Badge } from "../design-system/primitives/Badge";
import { Button } from "../design-system/primitives/Button";
import { Panel } from "../design-system/primitives/Panel";
import { StatusChip } from "../design-system/primitives/StatusChip";
import { TableToolbar } from "../design-system/data/TableToolbar";
import { Tabs } from "../design-system/primitives/Tabs";
import styles from "./providers.module.css";
import { ProviderForm } from "./providers/ProviderForm";
import {
  EMPTY_PROVIDER_DRAFT,
  type ProviderDraft,
  validateProviderDraft,
} from "./providers/providerPresets";

export function ProvidersPage() {
  const [tab, setTab] = useState<string | null>("providers");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Provider | null>(null);

  function openCreate() {
    setEditing(null);
    setFormOpen(true);
  }

  function openEdit(provider: Provider) {
    setEditing(provider);
    setFormOpen(true);
  }

  return (
    <ListPage
      title="Providers"
      subtitle="Model endpoints and routing"
      actions={
        <Button
          leftSection={<RiAddLine size={16} />}
          onClick={openCreate}
        >
          New provider
        </Button>
      }
    >
      <Tabs value={tab} onChange={setTab}>
        <Tabs.List>
          <Tabs.Tab value="providers">Providers</Tabs.Tab>
          <Tabs.Tab value="models">Models</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="providers" pt="md">
          <ProvidersTab onEdit={openEdit} onCreate={openCreate} />
        </Tabs.Panel>
        <Tabs.Panel value="models" pt="md">
          <ModelsTab />
        </Tabs.Panel>
      </Tabs>
      <ProviderFormDrawer
        opened={formOpen}
        provider={editing}
        onClose={() => setFormOpen(false)}
      />
    </ListPage>
  );
}

function ProvidersTab({
  onEdit,
  onCreate,
}: {
  onEdit: (provider: Provider) => void;
  onCreate: () => void;
}) {
  const { data: providers } = useProviders();
  const del = useDeleteProvider();
  const refresh = useRefreshModels();
  const [providerToDelete, setProviderToDelete] = useState<Provider | null>(
    null,
  );

  async function onRefresh(id: string) {
    try {
      const models = await refresh.mutateAsync(id);
      notifications.show({ message: `Refreshed ${models.length} models` });
    } catch {
      notifications.show({ message: "Failed to refresh models", color: "red" });
    }
  }

  if ((providers ?? []).length === 0) {
    return (
      <GuidedEmptyState
        icon={RiAddLine}
        title="No providers yet"
        description="Connect a model endpoint to discover models and create agents."
        helpId="provider.kind"
        action={<Button onClick={onCreate}>Add your first provider</Button>}
      />
    );
  }

  return (
    <>
      <DataTable<Provider>
        rowKey={(provider) => provider.id}
        rows={providers ?? []}
        columns={[
          { key: "name", header: "Name", render: (provider) => provider.name },
          {
            key: "kind",
            header: "Kind",
            render: (provider) => <Badge tone="info">{provider.kind}</Badge>,
          },
          {
            key: "status",
            header: "Status",
            render: () => <StatusChip tone="success">ready</StatusChip>,
          },
          {
            key: "actions",
            header: "Actions",
            render: (provider) => (
              <div className={styles.actions}>
                <IconButton
                  label="Refresh models"
                  icon={RiRefreshLine}
                  size={16}
                  onClick={() => onRefresh(provider.id)}
                />
                <IconButton
                  label="Edit"
                  icon={RiSettings3Line}
                  size={16}
                  onClick={() => onEdit(provider)}
                />
                <IconButton
                  label="Delete"
                  icon={RiDeleteBin6Line}
                  size={16}
                  color="red"
                  onClick={() => setProviderToDelete(provider)}
                />
              </div>
            ),
          },
        ]}
      />
      <ConfirmDialog
        opened={providerToDelete !== null}
        title="Delete provider?"
        description={`Delete "${providerToDelete?.name ?? ""}" permanently? This cannot be undone.`}
        requireText={providerToDelete?.name}
        confirmLabel="Delete"
        danger
        onConfirm={async () => {
          if (!providerToDelete) return;
          await del.mutateAsync(providerToDelete.id);
          setProviderToDelete(null);
        }}
        onClose={() => setProviderToDelete(null)}
      />
    </>
  );
}

function ProviderFormDrawer({
  opened,
  provider,
  onClose,
}: {
  opened: boolean;
  provider: Provider | null;
  onClose: () => void;
}) {
  const create = useCreateProvider();
  const update = useUpdateProvider();
  const [draft, setDraft] = useState<ProviderDraft>(EMPTY_PROVIDER_DRAFT);
  const [errors, setErrors] = useState<
    Partial<Record<keyof ProviderDraft, string>>
  >({});

  useEffect(() => {
    if (!opened) return;
    setDraft({
      name: provider?.name ?? "",
      kind: provider?.kind ?? "generic",
      baseUrl: provider?.base_url ?? "",
      modelsUrl: provider?.models_url ?? "",
      apiKey: "",
    });
    setErrors({});
  }, [opened, provider]);

  async function onSave() {
    const nextErrors = validateProviderDraft(draft);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;
    try {
      if (provider) {
        await update.mutateAsync({
          pid: provider.id,
          body: {
            name: draft.name,
            kind: draft.kind,
            base_url: draft.baseUrl,
            models_url: draft.modelsUrl,
            ...(draft.apiKey ? { api_key: draft.apiKey } : {}),
          },
        });
        notifications.show({ message: "Provider updated" });
      } else {
        await create.mutateAsync({
          name: draft.name,
          kind: draft.kind,
          base_url: draft.baseUrl || undefined,
          api_key: draft.apiKey || undefined,
          models_url: draft.modelsUrl || undefined,
        });
        notifications.show({ message: "Provider created" });
      }
      onClose();
    } catch {
      notifications.show({
        message: provider ? "Failed to update provider" : "Failed to create provider",
        color: "red",
      });
    }
  }

  return (
    <Drawer
      opened={opened}
      onClose={onClose}
      title={provider ? "Edit provider" : "New provider"}
      size="md"
    >
      <ProviderForm
        value={draft}
        onChange={setDraft}
        providerId={provider?.id}
        errors={errors}
      />
      <div className={styles.formActions}>
        <Button variant="light" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={onSave} loading={create.isPending || update.isPending}>
          {provider ? "Save" : "Create provider"}
        </Button>
      </div>
    </Drawer>
  );
}

function ModelsTab() {
  const { data: models } = useModels();
  const { data: providers } = useProviders();
  const create = useCreateModel();
  const del = useDeleteModel();
  const { data: labels } = useLabels();
  const [providerId, setProviderId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [contextWindow, setContextWindow] = useState<number | string>("");
  const [labelFilter, setLabelFilter] = useState<string | null>(null);
  const [editing, setEditing] = useState<Model | null>(null);
  const [labelsOpen, setLabelsOpen] = useState(false);
  const [modelToDelete, setModelToDelete] = useState<Model | null>(null);

  const visibleModels = (models ?? []).filter(
    (model) =>
      !labelFilter || model.labels.some((label) => label.name === labelFilter),
  );

  function providerName(id: string) {
    return providers?.find((provider) => provider.id === id)?.name ?? id;
  }

  async function onCreate() {
    if (!providerId || !name) return;
    try {
      await create.mutateAsync({
        provider_id: providerId,
        name,
        context_window:
          contextWindow === "" ? undefined : Number(contextWindow),
        labels: [],
      });
      setName("");
      setContextWindow("");
    } catch {
      notifications.show({ message: "Failed to create model", color: "red" });
    }
  }

  return (
    <div className={styles.modelsLayout}>
      <Panel>
        <Panel.Header>Add model</Panel.Header>
        <Panel.Body>
          <div className={styles.modelForm}>
            <FormField label="Provider" required>
              <Select
                data={(providers ?? []).map((provider) => ({
                  value: provider.id,
                  label: provider.name,
                }))}
                value={providerId}
                onChange={setProviderId}
              />
            </FormField>
            <FormField label="Model name" required>
              <TextInput
                value={name}
                onChange={(e) => setName(e.currentTarget.value)}
              />
            </FormField>
            <FormField
              label="Context window"
              description="Optional token window for custom/local models"
            >
              <NumberInput
                min={1}
                value={contextWindow}
                onChange={setContextWindow}
              />
            </FormField>
            <Button onClick={onCreate} loading={create.isPending}>
              Create model
            </Button>
          </div>
        </Panel.Body>
      </Panel>

      <TableToolbar>
        <Select
          label="Filter by label"
          clearable
          data={(labels ?? []).map((label) => label.name)}
          value={labelFilter}
          onChange={setLabelFilter}
          w={220}
        />
      </TableToolbar>

      <DataTable<Model>
        rowKey={(model) => model.id}
        rows={visibleModels}
        columns={[
          {
            key: "provider",
            header: "Provider",
            render: (model) => providerName(model.provider_id),
          },
          { key: "name", header: "Name", render: (model) => model.name },
          {
            key: "context",
            header: "Context window",
            render: (model) => model.context_window ?? "—",
          },
          {
            key: "labels",
            header: "Labels",
            render: (model) => (
              <div className={styles.labels}>
                {model.labels.map((label) => (
                  <Badge key={label.id} tone="agent">
                    {label.name}
                  </Badge>
                ))}
              </div>
            ),
          },
          {
            key: "actions",
            header: "Actions",
            render: (model) => (
              <div className={styles.actions}>
                <Button
                  size="compact-xs"
                  variant="light"
                  onClick={() => {
                    setEditing(model);
                    setLabelsOpen(true);
                  }}
                >
                  Edit labels
                </Button>
                <IconButton
                  label="Delete"
                  icon={RiDeleteBin6Line}
                  size={16}
                  color="red"
                  onClick={() => setModelToDelete(model)}
                />
              </div>
            ),
          },
        ]}
      />

      <ModelLabelsModal
        model={editing}
        opened={labelsOpen}
        onClose={() => setLabelsOpen(false)}
      />
      <ConfirmDialog
        opened={modelToDelete !== null}
        title="Delete model?"
        description={`Delete "${modelToDelete?.name ?? ""}" permanently? This cannot be undone.`}
        confirmLabel="Delete"
        danger
        onConfirm={async () => {
          if (!modelToDelete) return;
          await del.mutateAsync(modelToDelete.id);
          setModelToDelete(null);
        }}
        onClose={() => setModelToDelete(null)}
      />
    </div>
  );
}

function ModelLabelsModal({
  model,
  opened,
  onClose,
}: {
  model: Model | null;
  opened: boolean;
  onClose: () => void;
}) {
  const { data: labels } = useLabels();
  const setLabels = useSetModelLabels();
  const [rows, setRows] = useState<{ label: string; priority: number }[]>([]);

  useEffect(() => {
    setRows(
      model
        ? model.labels.map((label) => ({
            label: label.name,
            priority: label.priority,
          }))
        : [],
    );
  }, [model]);

  async function onSave() {
    if (!model) return;
    try {
      await setLabels.mutateAsync({
        mid: model.id,
        labels: rows.filter((row) => row.label.trim()),
      });
      onClose();
    } catch {
      notifications.show({ message: "Failed to save labels", color: "red" });
    }
  }

  const used = new Set(rows.map((row) => row.label.trim().toLowerCase()));
  const suggestions = (labels ?? []).filter((label) => !used.has(label.name));

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={model ? `Labels — ${model.name}` : "Labels"}
    >
      {rows.map((row, index) => (
        <div key={index} className={styles.labelRow}>
          <TextInput
            label="Label"
            value={row.label}
            onChange={(e) => {
              const value = e.currentTarget.value;
              setRows((prev) =>
                prev.map((item, i) =>
                  i === index ? { ...item, label: value } : item,
                ),
              );
            }}
          />
          <NumberInput
            label="Priority"
            value={row.priority}
            onChange={(value) =>
              setRows((prev) =>
                prev.map((item, i) =>
                  i === index
                    ? { ...item, priority: Number(value) || 0 }
                    : item,
                ),
              )
            }
          />
          <Button
            color="red"
            variant="subtle"
            onClick={() =>
              setRows((prev) => prev.filter((_, i) => i !== index))
            }
          >
            Remove
          </Button>
        </div>
      ))}
      <Button
        variant="light"
        onClick={() =>
          setRows((prev) => [...prev, { label: "", priority: 0 }])
        }
      >
        Add label
      </Button>
      {suggestions.length > 0 && (
        <div className={styles.labels} style={{ marginTop: 12 }}>
          {suggestions.map((label) => (
            <Badge
              key={label.id}
              tone="agent"
              onClick={() =>
                setRows((prev) => [...prev, { label: label.name, priority: 0 }])
              }
            >
              {label.name}
            </Badge>
          ))}
        </div>
      )}
      <div className={styles.formActions}>
        <Button onClick={onSave} loading={setLabels.isPending}>
          Save
        </Button>
      </div>
    </Modal>
  );
}


