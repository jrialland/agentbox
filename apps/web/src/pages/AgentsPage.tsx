import {
  Button,
  Checkbox,
  MultiSelect,
  Select,
  Table,
  Textarea,
  TextInput,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import {
  useAgents,
  useCreateAgent,
  useDeleteAgent,
  useModels,
  useResetAvatar,
  useUploadAvatar,
} from "../api/queries";
import { AgentAvatar } from "../components/agents/AgentAvatar";

const NATIVE_TOOLS = ["read_text_file", "write_file", "list_directory"];

export function AgentsPage() {
  const { data: agents } = useAgents();
  const { data: models } = useModels();
  const create = useCreateAgent();
  const del = useDeleteAgent();
  const upload = useUploadAvatar();
  const reset = useResetAvatar();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [model, setModel] = useState<string | null>(null);
  const [tools, setTools] = useState<string[]>([]);
  const [mcpServers, setMcpServers] = useState<string[]>([]);
  const [mcpInput, setMcpInput] = useState("");
  const [subAgents, setSubAgents] = useState<string[]>([]);
  const [modes, setModes] = useState<{ name: string; write: boolean }[]>([
    { name: "ask", write: false },
    { name: "agent", write: true },
  ]);
  const [photo, setPhoto] = useState<File | null>(null);
  const [versions, setVersions] = useState<Record<string, number>>({});

  async function onCreate() {
    if (!model) return;
    const tool_bindings = [
      ...tools.map((t) => ({ name: t })),
      ...mcpServers.map((url) => ({ server_url: url })),
    ];
    const mode_definitions = modes.map((m) => ({
      name: m.name,
      flags: { write: m.write },
    }));
    try {
      const created = await create.mutateAsync({
        name,
        description,
        instructions,
        model,
        tool_bindings,
        mode_definitions,
        sub_agent_ids: subAgents,
      });
      if (photo) {
        await upload.mutateAsync({ name: created.name, file: photo });
        setVersions((v) => ({ ...v, [created.name]: (v[created.name] ?? 0) + 1 }));
      }
      setPhoto(null);
      setName("");
      setDescription("");
      setInstructions("");
      setModel(null);
      setTools([]);
      setMcpServers([]);
      setSubAgents([]);
    } catch {
      notifications.show({ message: "Failed to create agent", color: "red" });
    }
  }

  return (
    <div>
      <h1 className="title">Agents</h1>
      <div className="box">
        <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
        <TextInput
          label="Description"
          value={description}
          onChange={(e) => setDescription(e.currentTarget.value)}
        />
        <Textarea
          label="Instructions"
          value={instructions}
          onChange={(e) => setInstructions(e.currentTarget.value)}
        />
        <Select
          label="Model"
          data={[...new Set((models ?? []).map((m) => m.name))]}
          value={model}
          onChange={setModel}
        />
        <div>
          <p className="label">Native tools</p>
          {NATIVE_TOOLS.map((t) => (
            <Checkbox
              key={t}
              label={t}
              checked={tools.includes(t)}
              onChange={(e) => {
                const checked = e.currentTarget.checked;
                setTools((prev) =>
                  checked ? [...prev, t] : prev.filter((x) => x !== t),
                );
              }}
            />
          ))}
        </div>
        <div>
          <p className="label">MCP servers</p>
          <TextInput
            placeholder="https://server/mcp"
            value={mcpInput}
            onChange={(e) => setMcpInput(e.currentTarget.value)}
          />
          <Button
            size="xs"
            onClick={() => {
              if (mcpInput) {
                setMcpServers((prev) => [...prev, mcpInput]);
                setMcpInput("");
              }
            }}
          >
            Add MCP server
          </Button>
          <ul>
            {mcpServers.map((u, i) => (
              <li key={i}>
                {u}{" "}
                <button
                  type="button"
                  onClick={() => setMcpServers((p) => p.filter((_, j) => j !== i))}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="label">Modes</p>
          {modes.map((m, i) => (
            <div key={i}>
              <TextInput
                value={m.name}
                onChange={(e) => {
                  const value = e.currentTarget.value;
                  setModes((p) =>
                    p.map((x, j) => (j === i ? { ...x, name: value } : x)),
                  );
                }}
              />
              <Checkbox
                label="Write enabled"
                checked={m.write}
                onChange={(e) => {
                  const checked = e.currentTarget.checked;
                  setModes((p) =>
                    p.map((x, j) => (j === i ? { ...x, write: checked } : x)),
                  );
                }}
              />
            </div>
          ))}
        </div>
        <MultiSelect
          label="Sub-agents"
          data={[...new Set((agents ?? []).map((a) => a.name))]}
          value={subAgents}
          onChange={setSubAgents}
        />
        <div>
          <p className="label">Photo</p>
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            aria-label="Photo"
            onChange={(e) => setPhoto(e.currentTarget.files?.[0] ?? null)}
          />
        </div>
        <Button mt="md" onClick={onCreate} loading={create.isPending}>
          Create agent
        </Button>
      </div>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Name</Table.Th>
            <Table.Th>Avatar</Table.Th>
            <Table.Th>Description</Table.Th>
            <Table.Th>Actions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {(agents ?? []).map((a) => (
            <Table.Tr key={a.name}>
              <Table.Td>{a.name}</Table.Td>
              <Table.Td>
                <AgentAvatar name={a.name} version={versions[a.name] ?? 0} />
              </Table.Td>
              <Table.Td>{a.description}</Table.Td>
              <Table.Td>
                <input
                  id={`avatar-${a.name}`}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  aria-label={`Change photo ${a.name}`}
                  style={{ display: "none" }}
                  onChange={async (e) => {
                    const file = e.currentTarget.files?.[0];
                    if (!file) return;
                    try {
                      await upload.mutateAsync({ name: a.name, file });
                      setVersions((v) => ({
                        ...v,
                        [a.name]: (v[a.name] ?? 0) + 1,
                      }));
                    } catch {
                      notifications.show({
                        message: "Failed to upload photo",
                        color: "red",
                      });
                    }
                  }}
                />
                <Button
                  size="xs"
                  onClick={() => document.getElementById(`avatar-${a.name}`)?.click()}
                >
                  Change photo
                </Button>{" "}
                <Button
                  size="xs"
                  variant="light"
                  onClick={async () => {
                    await reset.mutateAsync(a.name);
                    setVersions((v) => ({
                      ...v,
                      [a.name]: (v[a.name] ?? 0) + 1,
                    }));
                  }}
                >
                  Remove photo
                </Button>{" "}
                <Button size="xs" color="red" onClick={() => del.mutate(a.name)}>
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
