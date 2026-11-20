import {
  Badge,
  Button,
  Group,
  Modal,
  NumberInput,
  Select,
  Table,
  Tabs,
  TextInput,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
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

const KINDS = [
  "generic",
  "openai_legacy",
  "openai_responses",
  "anthropic",
  "moonshot",
  "deepseek",
  "ollama",
];

export function ProvidersPage() {
  return (
    <div>
      <h1 className="title">Providers</h1>
      <Tabs defaultValue="providers">
        <Tabs.List>
          <Tabs.Tab value="providers">Providers</Tabs.Tab>
          <Tabs.Tab value="models">Models</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="providers" pt="md">
          <ProvidersTab />
        </Tabs.Panel>
        <Tabs.Panel value="models" pt="md">
          <ModelsTab />
        </Tabs.Panel>
      </Tabs>
    </div>
  );
}

function ProvidersTab() {
  const { data: providers } = useProviders();
  const create = useCreateProvider();
  const del = useDeleteProvider();
  const refresh = useRefreshModels();
  const [name, setName] = useState("");
  const [kind, setKind] = useState<string | null>("generic");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [modelsUrl, setModelsUrl] = useState("");
  const [editing, setEditing] = useState<Provider | null>(null);

  async function onCreate() {
    try {
      await create.mutateAsync({
        name,
        kind: kind ?? "generic",
        base_url: baseUrl || undefined,
        api_key: apiKey || undefined,
        models_url: modelsUrl || undefined,
      });
      setName("");
      setBaseUrl("");
      setApiKey("");
      setModelsUrl("");
    } catch {
      notifications.show({ message: "Failed to create provider", color: "red" });
    }
  }

  async function onRefresh(id: string) {
    try {
      const models = await refresh.mutateAsync(id);
      notifications.show({ message: `Refreshed ${models.length} models` });
    } catch {
      notifications.show({ message: "Failed to refresh models", color: "red" });
    }
  }

  return (
    <div>
      <div className="box">
        <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
        <Select label="Kind" data={KINDS} value={kind} onChange={setKind} />
        <TextInput label="Base URL" value={baseUrl} onChange={(e) => setBaseUrl(e.currentTarget.value)} />
        <TextInput label="API key" value={apiKey} onChange={(e) => setApiKey(e.currentTarget.value)} />
        <TextInput label="Models URL" value={modelsUrl} onChange={(e) => setModelsUrl(e.currentTarget.value)} />
        <Button mt="md" onClick={onCreate} loading={create.isPending}>
          Create provider
        </Button>
      </div>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Name</Table.Th>
            <Table.Th>Kind</Table.Th>
            <Table.Th>Actions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {(providers ?? []).map((p) => (
            <Table.Tr key={p.id}>
              <Table.Td>{p.name}</Table.Td>
              <Table.Td>{p.kind}</Table.Td>
              <Table.Td>
                <Button size="xs" onClick={() => onRefresh(p.id)}>
                  Refresh models
                </Button>{" "}
                <Button size="xs" variant="light" onClick={() => setEditing(p)}>
                  Edit
                </Button>{" "}
                <Button size="xs" color="red" onClick={() => del.mutate(p.id)}>
                  Delete
                </Button>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {editing && (
        <ProviderEditModal provider={editing} onClose={() => setEditing(null)} />
      )}
    </div>
  );
}

function ProviderEditModal({
  provider,
  onClose,
}: {
  provider: Provider;
  onClose: () => void;
}) {
  const update = useUpdateProvider();
  const [name, setName] = useState(provider.name);
  const [kind, setKind] = useState<string | null>(provider.kind);
  const [baseUrl, setBaseUrl] = useState(provider.base_url ?? "");
  const [apiKey, setApiKey] = useState("");
  const [modelsUrl, setModelsUrl] = useState(provider.models_url ?? "");

  async function onSave() {
    try {
      await update.mutateAsync({
        pid: provider.id,
        body: {
          name,
          kind: kind ?? provider.kind,
          base_url: baseUrl,
          models_url: modelsUrl,
          ...(apiKey ? { api_key: apiKey } : {}),
        },
      });
      onClose();
    } catch {
      notifications.show({ message: "Failed to update provider", color: "red" });
    }
  }

  return (
    <Modal opened onClose={onClose} title="Edit provider">
      <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
      <Select label="Kind" data={KINDS} value={kind} onChange={setKind} />
      <TextInput label="Base URL" value={baseUrl} onChange={(e) => setBaseUrl(e.currentTarget.value)} />
      <TextInput
        label="API key"
        placeholder="leave blank to keep"
        value={apiKey}
        onChange={(e) => setApiKey(e.currentTarget.value)}
      />
      <TextInput label="Models URL" value={modelsUrl} onChange={(e) => setModelsUrl(e.currentTarget.value)} />
      <Button mt="md" onClick={onSave}>
        Save
      </Button>
    </Modal>
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
        <Group key={index} align="end">
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
                  i === index ? { ...item, priority: Number(value) || 0 } : item,
                ),
              )
            }
          />
          <Button
            color="red"
            variant="subtle"
            onClick={() => setRows((prev) => prev.filter((_, i) => i !== index))}
          >
            Remove
          </Button>
        </Group>
      ))}
      <Button
        variant="light"
        onClick={() => setRows((prev) => [...prev, { label: "", priority: 0 }])}
      >
        Add label
      </Button>
      {suggestions.length > 0 && (
        <Group mt="sm">
          {suggestions.map((label) => (
            <Badge
              key={label.id}
              style={{ cursor: "pointer" }}
              onClick={() =>
                setRows((prev) => [...prev, { label: label.name, priority: 0 }])
              }
            >
              {label.name}
            </Badge>
          ))}
        </Group>
      )}
      <Button mt="md" onClick={onSave} loading={setLabels.isPending}>
        Save
      </Button>
    </Modal>
  );
}

function ModelsTab() {
  const { data: models } = useModels();
  const { data: providers } = useProviders();
  const create = useCreateModel();
  const del = useDeleteModel();
  const [providerId, setProviderId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [contextWindow, setContextWindow] = useState<number | string>("");
  const { data: labels } = useLabels();
  const [labelFilter, setLabelFilter] = useState<string | null>(null);
  const [editing, setEditing] = useState<Model | null>(null);
  const [labelsOpen, setLabelsOpen] = useState(false);

  const visibleModels = (models ?? []).filter(
    (model) =>
      !labelFilter || model.labels.some((label) => label.name === labelFilter),
  );

  function providerName(id: string) {
    return providers?.find((p) => p.id === id)?.name ?? id;
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
    <div>
      <div className="box">
        <Select
          label="Provider"
          data={(providers ?? []).map((p) => ({ value: p.id, label: p.name }))}
          value={providerId}
          onChange={setProviderId}
        />
        <TextInput
          label="Model name"
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
        />
        <NumberInput
          label="Context window"
          description="Optional token window for custom/local models"
          min={1}
          value={contextWindow}
          onChange={setContextWindow}
        />
        <Button mt="md" onClick={onCreate} loading={create.isPending}>
          Create model
        </Button>
      </div>
      <Select
        label="Filter by label"
        clearable
        data={(labels ?? []).map((label) => label.name)}
        value={labelFilter}
        onChange={setLabelFilter}
      />
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Provider</Table.Th>
            <Table.Th>Name</Table.Th>
            <Table.Th>Context window</Table.Th>
            <Table.Th>Labels</Table.Th>
            <Table.Th>Actions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {visibleModels.map((m) => (
            <Table.Tr key={m.id}>
              <Table.Td>{providerName(m.provider_id)}</Table.Td>
              <Table.Td>{m.name}</Table.Td>
              <Table.Td>{m.context_window ?? ""}</Table.Td>
              <Table.Td>
                {m.labels.map((label) => (
                  <Badge key={label.id} mr={4}>
                    {label.name}
                  </Badge>
                ))}
              </Table.Td>
              <Table.Td>
                <Button
                  size="xs"
                  variant="light"
                  mr={4}
                  onClick={() => {
                    setEditing(m);
                    setLabelsOpen(true);
                  }}
                >
                  Edit labels
                </Button>
                <Button size="xs" color="red" onClick={() => del.mutateAsync(m.id)}>
                  Delete
                </Button>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <ModelLabelsModal
        model={editing}
        opened={labelsOpen}
        onClose={() => setLabelsOpen(false)}
      />
    </div>
  );
}
