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

import { useAgents, useCreateAgent, useDeleteAgent, useModels } from "../api/queries";

const NATIVE_TOOLS = ["read_text_file", "write_file", "list_directory"];

export function AgentsPage() {
  const { data: agents } = useAgents();
  const { data: models } = useModels();
  const create = useCreateAgent();
  const del = useDeleteAgent();

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
      await create.mutateAsync({
        name,
        description,
        instructions,
        model,
        tool_bindings,
        mode_definitions,
        sub_agent_ids: subAgents,
      });
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
          data={(models ?? []).map((m) => m.name)}
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
              onChange={(e) =>
                setTools((prev) =>
                  e.currentTarget.checked ? [...prev, t] : prev.filter((x) => x !== t),
                )
              }
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
                onChange={(e) =>
                  setModes((p) =>
                    p.map((x, j) =>
                      j === i ? { ...x, name: e.currentTarget.value } : x,
                    ),
                  )
                }
              />
              <Checkbox
                label="Write enabled"
                checked={m.write}
                onChange={(e) =>
                  setModes((p) =>
                    p.map((x, j) =>
                      j === i ? { ...x, write: e.currentTarget.checked } : x,
                    ),
                  )
                }
              />
            </div>
          ))}
        </div>
        <MultiSelect
          label="Sub-agents"
          data={(agents ?? []).map((a) => a.name)}
          value={subAgents}
          onChange={setSubAgents}
        />
        <Button mt="md" onClick={onCreate} loading={create.isPending}>
          Create agent
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
          {(agents ?? []).map((a) => (
            <Table.Tr key={a.name}>
              <Table.Td>{a.name}</Table.Td>
              <Table.Td>{a.description}</Table.Td>
              <Table.Td>
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
