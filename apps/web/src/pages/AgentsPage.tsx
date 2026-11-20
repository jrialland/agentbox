import {
  Badge,
  Button,
  Checkbox,
  Modal,
  MultiSelect,
  Select,
  Table,
  Textarea,
  TextInput,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import {
  useAgentCard,
  useAgents,
  useCreateAgent,
  useDeleteAgentCard,
  useDeleteAgent,
  useLabels,
  useModels,
  usePreviewPrompt,
  useProviders,
  useResetAvatar,
  useSetAgentCard,
  useUploadAvatar,
} from "../api/queries";
import { AgentAvatar } from "../components/agents/AgentAvatar";

export const NATIVE_TOOLS = [
  "read_text_file",
  "read_media_file",
  "read_multiple_files",
  "list_directory",
  "list_directory_with_sizes",
  "directory_tree",
  "search_files",
  "get_file_info",
  "list_allowed_directories",
  "write_file",
  "append_file",
  "edit_file",
  "create_directory",
  "move_file",
  "copy_file",
  "delete_path",
  "web_search",
  "fetch_url",
  "terminal",
];

export const TERMINAL_TOOLS = [
  "run_command",
  "list_jobs",
  "get_job_output",
  "kill_job",
];

export function buildToolBindings(tools: string[]) {
  return tools.flatMap((tool) =>
    tool === "terminal"
      ? TERMINAL_TOOLS.map((name) => ({ name }))
      : [{ name: tool }],
  );
}

function TemplatePreviewModal({
  initialTemplate,
  onApply,
  onClose,
}: {
  initialTemplate: string;
  onApply: (template: string) => void;
  onClose: () => void;
}) {
  const preview = usePreviewPrompt();
  const [template, setTemplate] = useState(initialTemplate);
  const [context, setContext] = useState<Record<string, string>>({});
  const [result, setResult] = useState<{
    rendered: string;
    missing: string[];
    error: { message: string; line?: number | null } | null;
    variables: string[];
  } | null>(null);

  async function renderNow() {
    const data = await preview.mutateAsync({ template, context });
    setContext(data.context);
    setResult(data);
  }

  return (
    <Modal opened onClose={onClose} title="Test prompt template" size="xl">
      <Textarea
        label="Template"
        minRows={6}
        value={template}
        onChange={(e) => setTemplate(e.currentTarget.value)}
      />
      <Button mt="sm" onClick={renderNow} loading={preview.isPending}>
        Render
      </Button>
      {result && (
        <>
          {result.error && (
            <div role="alert" style={{ color: "red" }}>
              {result.error.message}
              {result.error.line ? ` (line ${result.error.line})` : ""}
            </div>
          )}
          {result.missing.length > 0 && (
            <div role="status" style={{ color: "orange" }}>
              Missing: {result.missing.join(", ")}
            </div>
          )}
          <Textarea
            label="Rendered"
            minRows={6}
            readOnly
            value={result.rendered}
          />
          {result.variables.map((path) => (
            <TextInput
              key={path}
              label={path}
              value={context[path] ?? ""}
              onChange={(e) => {
                const value = e.currentTarget.value;
                setContext((prev) => ({ ...prev, [path]: value }));
              }}
            />
          ))}
        </>
      )}
      <Button
        mt="md"
        onClick={() => {
          onApply(template);
          onClose();
        }}
      >
        Apply to instructions
      </Button>
    </Modal>
  );
}

export function AgentsPage() {
  const { data: agents } = useAgents();
  const { data: models } = useModels();
  const { data: labels } = useLabels();
  const { data: providers } = useProviders();
  const create = useCreateAgent();
  const del = useDeleteAgent();
  const upload = useUploadAvatar();
  const reset = useResetAvatar();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [modelRef, setModelRef] = useState<string | null>(null);
  const providerName = (id: string) =>
    providers?.find((provider) => provider.id === id)?.name ?? id;
  const modelOptions = [
    ...(models ?? []).map((model) => ({
      value: `model:${model.id}`,
      label: `${providerName(model.provider_id)} · ${model.name}`,
    })),
    ...(labels ?? []).map((label) => ({
      value: `label:${label.name}`,
      label: `label: ${label.name}`,
    })),
  ];
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
  const [cardAgent, setCardAgent] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  async function onCreate() {
    if (!modelRef) return;
    const isLabel = modelRef.startsWith("label:");
    const modelName = isLabel
      ? undefined
      : models?.find((model) => `model:${model.id}` === modelRef)?.name;
    const tool_bindings = [
      ...buildToolBindings(tools),
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
        model: modelName,
        model_label: isLabel ? modelRef.slice("label:".length) : undefined,
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
      setModelRef(null);
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
        <Button variant="light" mt="xs" onClick={() => setPreviewOpen(true)}>
          Test template
        </Button>
        <Select
          label="Model"
          data={modelOptions}
          value={modelRef}
          onChange={setModelRef}
          searchable
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
            <Table.Th>Model</Table.Th>
            <Table.Th>Label</Table.Th>
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
              <Table.Td>{a.model_binding.model}</Table.Td>
              <Table.Td>{a.model_label ? <Badge>{a.model_label}</Badge> : null}</Table.Td>
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
                <Button size="xs" variant="light" onClick={() => setCardAgent(a.name)}>
                  A2A
                </Button>{" "}
                <Button size="xs" color="red" onClick={() => del.mutate(a.name)}>
                  Delete
                </Button>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {previewOpen && (
        <TemplatePreviewModal
          initialTemplate={instructions}
          onApply={setInstructions}
          onClose={() => setPreviewOpen(false)}
        />
      )}
      {cardAgent && (
        <AgentCardModal name={cardAgent} onClose={() => setCardAgent(null)} />
      )}
    </div>
  );
}


function AgentCardModal({
  name,
  onClose,
}: {
  name: string;
  onClose: () => void;
}) {
  const { data: card } = useAgentCard(name);
  const save = useSetAgentCard();
  const remove = useDeleteAgentCard();
  const [text, setText] = useState<string | null>(null);
  const initial = JSON.stringify(
    card ?? { name, description: "", version: "1.0.0", skills: [] },
    null,
    2,
  );
  const value = text ?? initial;

  async function onSave() {
    try {
      const parsed = JSON.parse(value);
      await save.mutateAsync({ name, card: parsed });
      onClose();
    } catch {
      notifications.show({ message: "Invalid agent card JSON", color: "red" });
    }
  }

  return (
    <Modal opened onClose={onClose} title={`A2A card: ${name}`} size="lg">
      <Textarea
        label="Agent card (JSON)"
        minRows={12}
        value={value}
        onChange={(e) => setText(e.currentTarget.value)}
      />
      <Button mt="md" onClick={onSave}>
        Save
      </Button>{" "}
      <Button
        mt="md"
        variant="light"
        color="red"
        onClick={async () => {
          await remove.mutateAsync(name);
          onClose();
        }}
      >
        Remove
      </Button>
    </Modal>
  );
}
