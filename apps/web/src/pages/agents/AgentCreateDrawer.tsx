import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { useCreateAgent, useLabels, useModels, useProviders, useUploadAvatar } from "../../api/queries";
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
import { requiredText } from "../../lib/validation";
import { buildToolBindings } from "../AgentsPage";
import { AgentToolsEditor } from "./AgentToolsEditor";
import { AgentModesEditor } from "./AgentModesEditor";
import { AgentMcpEditor } from "./AgentMcpEditor";
import { validateMcpUrl, validateModes } from "./agentFormValidation";
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
  const [subAgents, setSubAgents] = useState<string[]>([]);
  const [modes, setModes] = useState<{ name: string; write: boolean }[]>([
    { name: "ask", write: false },
    { name: "agent", write: true },
  ]);
  const [photo, setPhoto] = useState<File | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

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
    const next: Record<string, string> = {};
    const nameError = requiredText(name, "Name");
    if (nameError) next.name = nameError;
    if (!modelRef) next.model = "Choose a model.";
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    if (!modelRef) return;
    const modesError = validateModes(modes);
    const mcpError = mcpServers.map(validateMcpUrl).find(Boolean) ?? null;
    if (modesError || mcpError) return;
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
      setErrors({});
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
        <FormField label="Name" required error={errors.name}>
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
        <FormField label="Model" required error={errors.model}>
          <Select
            data={modelOptions}
            value={modelRef}
            onChange={setModelRef}
            searchable
          />
        </FormField>
      </Section>

      <Section title="Capabilities">
        <AgentToolsEditor value={tools} onChange={setTools} />
        <AgentMcpEditor value={mcpServers} onChange={setMcpServers} />      </Section>

      <Section title="Behavior">
        <AgentModesEditor value={modes} onChange={setModes} />      </Section>

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


