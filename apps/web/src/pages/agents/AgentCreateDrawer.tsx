import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { useCreateAgent, useLabels, useModels, useProviders, useUploadAvatar } from "../../api/queries";
import { Checkbox } from "../../design-system/forms/Checkbox";
import { FileDropzone } from "../../design-system/forms/FileDropzone";
import { FormActions } from "../../design-system/forms/FormActions";
import { FormField } from "../../design-system/forms/FormField";
import { MultiSelect } from "../../design-system/forms/MultiSelect";
import { Select } from "../../design-system/forms/Select";
import { TextInput } from "../../design-system/forms/TextInput";
import { Textarea } from "../../design-system/forms/Textarea";
import { Drawer } from "../../design-system/overlays/Drawer";
import { Button } from "../../design-system/primitives/Button";
import { Section } from "../../design-system/primitives/Section";
import {
  buildToolBindings,
  NATIVE_TOOLS,
  TERMINAL_TOOLS,
} from "../AgentsPage";
import styles from "./agents.module.css";
import { TemplatePreviewModal } from "./TemplatePreviewModal";

export function AgentCreateDrawer({
  opened,
  onClose,
  subAgentOptions,
}: {
  opened: boolean;
  onClose: () => void;
  subAgentOptions: string[];
}) {
  const { data: models } = useModels();
  const { data: labels } = useLabels();
  const { data: providers } = useProviders();
  const create = useCreateAgent();
  const upload = useUploadAvatar();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [modelRef, setModelRef] = useState<string | null>(null);
  const [tools, setTools] = useState<string[]>([]);
  const [mcpServers, setMcpServers] = useState<string[]>([]);
  const [mcpInput, setMcpInput] = useState("");
  const [subAgents, setSubAgents] = useState<string[]>([]);
  const [modes, setModes] = useState<{ name: string; write: boolean }[]>([
    { name: "ask", write: false },
    { name: "agent", write: true },
  ]);
  const [photo, setPhoto] = useState<File | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

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
    const mode_definitions = modes.map((mode) => ({
      name: mode.name,
      flags: { write: mode.write },
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
      }
      setName("");
      setDescription("");
      setInstructions("");
      setModelRef(null);
      setTools([]);
      setMcpServers([]);
      setSubAgents([]);
      setPhoto(null);
      onClose();
    } catch {
      notifications.show({ message: "Failed to create agent", color: "red" });
    }
  }

  return (
    <Drawer opened={opened} onClose={onClose} title="New agent" size="lg">
      <Section title="Identity">
        <FormField label="Name" required>
          <TextInput
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
          />
        </FormField>
        <FormField label="Description">
          <TextInput
            value={description}
            onChange={(e) => setDescription(e.currentTarget.value)}
          />
        </FormField>
        <FormField label="Instructions">
          <Textarea
            minRows={4}
            value={instructions}
            onChange={(e) => setInstructions(e.currentTarget.value)}
          />
          <Button
            variant="light"
            size="compact-sm"
            mt="xs"
            onClick={() => setPreviewOpen(true)}
          >
            Test template
          </Button>
        </FormField>
        <FormField label="Model" required>
          <Select
            data={modelOptions}
            value={modelRef}
            onChange={setModelRef}
            searchable
          />
        </FormField>
      </Section>

      <Section title="Capabilities">
        <div className={styles.toolGrid}>
          {NATIVE_TOOLS.map((tool) => (
            <Checkbox
              key={tool}
              label={tool}
              checked={tools.includes(tool)}
              onChange={(e) => {
                const checked = e.currentTarget.checked;
                setTools((prev) =>
                  checked ? [...prev, tool] : prev.filter((x) => x !== tool),
                );
              }}
            />
          ))}
        </div>
        <FormField label="MCP servers" description="Add one MCP server URL at a time.">
          <div className={styles.inlineForm}>
            <TextInput
              placeholder="https://server/mcp"
              value={mcpInput}
              onChange={(e) => setMcpInput(e.currentTarget.value)}
            />
            <Button
              variant="light"
              onClick={() => {
                if (mcpInput) {
                  setMcpServers((prev) => [...prev, mcpInput]);
                  setMcpInput("");
                }
              }}
            >
              Add
            </Button>
          </div>
          <ul className={styles.inlineList}>
            {mcpServers.map((url, index) => (
              <li key={index}>
                <code>{url}</code>
                <Button
                  variant="subtle"
                  color="red"
                  size="compact-xs"
                  onClick={() =>
                    setMcpServers((prev) =>
                      prev.filter((_, i) => i !== index),
                    )
                  }
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        </FormField>
      </Section>

      <Section title="Behavior">
        <FormField label="Modes" description="Each mode defines whether write tools are enabled.">
          <div className={styles.modes}>
            {modes.map((mode, index) => (
              <div key={index} className={styles.modeRow}>
                <TextInput
                  value={mode.name}
                  aria-label={`Mode ${index + 1} name`}
                  onChange={(e) => {
                    const value = e.currentTarget.value;
                    setModes((prev) =>
                      prev.map((item, i) =>
                        i === index ? { ...item, name: value } : item,
                      ),
                    );
                  }}
                />
                <Checkbox
                  label="Write enabled"
                  checked={mode.write}
                  onChange={(e) => {
                    const checked = e.currentTarget.checked;
                    setModes((prev) =>
                      prev.map((item, i) =>
                        i === index ? { ...item, write: checked } : item,
                      ),
                    );
                  }}
                />
              </div>
            ))}
          </div>
        </FormField>
        <FormField label="Sub-agents">
          <MultiSelect
            data={subAgentOptions}
            value={subAgents}
            onChange={setSubAgents}
          />
        </FormField>
      </Section>

      <Section title="Presentation">
        <FormField label="Photo" description="PNG, JPEG, or WebP.">
          <FileDropzone
            accept="image/png,image/jpeg,image/webp"
            onFiles={(files) => setPhoto(files[0] ?? null)}
          />
          {photo && <span className={styles.fileName}>{photo.name}</span>}
        </FormField>
      </Section>

      <FormActions>
        <Button variant="light" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={onCreate} loading={create.isPending}>
          Create agent
        </Button>
      </FormActions>
      {previewOpen && (
        <TemplatePreviewModal
          initialTemplate={instructions}
          onApply={setInstructions}
          onClose={() => setPreviewOpen(false)}
        />
      )}
    </Drawer>
  );
}
