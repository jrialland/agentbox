import { Button, Modal, Select, Table, Tabs, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import type { Provider } from "../api/endpoints";
import {
  useCreateModel,
  useCreateProvider,
  useDeleteModel,
  useDeleteProvider,
  useModels,
  useProviders,
  useRefreshModels,
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

function ModelsTab() {
  const { data: models } = useModels();
  const { data: providers } = useProviders();
  const create = useCreateModel();
  const del = useDeleteModel();
  const [providerId, setProviderId] = useState<string | null>(null);
  const [name, setName] = useState("");

  function providerName(id: string) {
    return providers?.find((p) => p.id === id)?.name ?? id;
  }

  async function onCreate() {
    if (!providerId || !name) return;
    try {
      await create.mutateAsync({ provider_id: providerId, name, labels: [] });
      setName("");
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
        <Button mt="md" onClick={onCreate} loading={create.isPending}>
          Create model
        </Button>
      </div>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Provider</Table.Th>
            <Table.Th>Name</Table.Th>
            <Table.Th>Actions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {(models ?? []).map((m) => (
            <Table.Tr key={m.id}>
              <Table.Td>{providerName(m.provider_id)}</Table.Td>
              <Table.Td>{m.name}</Table.Td>
              <Table.Td>
                <Button size="xs" color="red" onClick={() => del.mutateAsync(m.id)}>
                  Delete
                </Button>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}
