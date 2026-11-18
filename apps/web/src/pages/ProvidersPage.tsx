import { Button, Select, Table, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import {
  useCreateProvider,
  useDeleteProvider,
  useProviders,
  useRefreshModels,
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
  const { data: providers } = useProviders();
  const create = useCreateProvider();
  const del = useDeleteProvider();
  const refresh = useRefreshModels();
  const [name, setName] = useState("");
  const [kind, setKind] = useState<string | null>("generic");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [modelsUrl, setModelsUrl] = useState("");

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
      <h1 className="title">Providers</h1>
      <div className="box">
        <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
        <Select label="Kind" data={KINDS} value={kind} onChange={setKind} />
        <TextInput
          label="Base URL"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.currentTarget.value)}
        />
        <TextInput
          label="API key"
          value={apiKey}
          onChange={(e) => setApiKey(e.currentTarget.value)}
        />
        <TextInput
          label="Models URL"
          value={modelsUrl}
          onChange={(e) => setModelsUrl(e.currentTarget.value)}
        />
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
                </Button>
                <Button size="xs" color="red" ml="xs" onClick={() => del.mutate(p.id)}>
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
