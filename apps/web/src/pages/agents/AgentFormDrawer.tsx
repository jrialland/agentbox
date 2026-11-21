import { notifications } from "@mantine/notifications";
import { useState } from "react";

import type { Agent } from "../../api/endpoints";
import {
  useCreateAgent,
  useLabels,
  useModels,
  useProviders,
  useUpdateAgent,
  useUploadAvatar,
} from "../../api/queries";
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
import { buildToolBindings, TERMINAL_TOOLS } from "../AgentsPage";
import { AgentMcpEditor } from "./AgentMcpEditor";
import { AgentModesEditor } from "./AgentModesEditor";
import { AgentToolsEditor } from "./AgentToolsEditor";
import styles from "./agents.module.css";
import { validateModes } from "./agentFormValidation";
import {
  fromBinding,
  toBinding,
  validateMcpServers,
  type McpServerDraft,
} from "./mcpTypes";
import { TemplatePreviewModal } from "./TemplatePreviewModal";

export function AgentFormDrawer({
  opened,
  onClose,
  subAgentOptions,
  agent,
}: {
  opened: boolean;
  onClose: () => void;
  subAgentOptions: string[];
  agent?: Agent;
}) {
  const { data: models } = useModels();
  const { data: labels } = useLabels();
  const { data: providers } = useProviders();
  const create = useCreateAgent();
  const update = useUpdateAgent();
  const upload = useUploadAvatar();
  const editing = agent !== undefined;

  const [name, setName] = useState(agent?.name ?? "");
  const [description, setDescription] = useState(agent?.description ?? "");
  const [instructions, setInstructions] = useState(agent?.instructions ?? "");

  const initialModelRef = (() => {
    if (!agent) return null;
    if (agent.model_label) return `label:${agent.model_label}`;
    const match = models?.find((model) => model.name === agent.model_binding.model);
    return `model:${match?.id ?? agent.model_binding.model}`;
  })();
  const [modelRef, setModelRef] = useState<string | null>(initialModelRef);

  const nativeNames =
    agent?.tool_bindings
      ?.filter(
        (binding) =>
          !("server_url" in binding) && !("command" in binding),
      )
      .map((binding) => ("name" in binding ? String(binding.name) : ""))
      .filter(Boolean) ?? [];
  const [tools, setTools] = useState<string[]>([
    ...nativeNames.filter((item) => !TERMINAL_TOOLS.includes(item)),
    ...(nativeNames.some((item) => TERMINAL_TOOLS.includes(item))
      ? ["terminal"]
      : []),
  ]);
  const [mcpServers, setMcpServers] = useState<McpServerDraft[]>(
    agent?.tool_bindings
      ?.map((binding) => fromBinding(binding as Record<string, unknown>))
      .filter((draft): draft is McpServerDraft => draft !== null) ?? [],
  );
  const [subAgents, setSubAgents] = useState<string[]>(
    agent?.sub_agent_ids ?? [],
  );
  const [modes, setModes] = useState<{ name: string; write: boolean }[]>(
    agent?.mode_definitions?.map((mode) => ({
      name: mode.name,
      write: Boolean(mode.flags.write),
    })) ?? [
      { name: "ask", write: false },
      { name: "agent", write: true },
    ],
  );
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
    ...(agent &&
    !agent.model_label &&
    !(models ?? []).some((model) => model.name === agent.model_binding.model)
      ? [
          {
            value: `model:${agent.model_binding.model}`,
            label: agent.model_binding.model,
          },
        ]
      : []),
    ...(labels ?? []).map((label) => ({
      value: `label:${label.name}`,
      label: `label: ${label.name}`,
    })),
  ];

  async function onSubmit() {
    const next: Record<string, string> = {};
    const nameError = requiredText(name, "Name");
    if (nameError) next.name = nameError;
    if (!modelRef) next.model = "Choose a model.";
    const modesError = validateModes(modes);
    if (modesError) next.modes = modesError;
    const mcpError = validateMcpServers(mcpServers);
    if (mcpError) next.mcp = mcpError;
    setErrors(next);
    if (Object.keys(next).length > 0 || !modelRef) return;

    const isLabel = modelRef.startsWith("label:");
    const modelName = isLabel
      ? undefined
      : models?.find((model) => `model:${model.id}` === modelRef)?.name ??
        modelRef.slice("model:".length);
    const tool_bindings = [
      ...buildToolBindings(tools),
      ...mcpServers.map(toBinding),
    ];
    const mode_definitions = modes.map((mode) => ({
      name: mode.name,
      flags: { write: mode.write },
    }));
    const body = {
      name,
      description,
      instructions,
      model: modelName,
      model_label: isLabel ? modelRef.slice("label:".length) : undefined,
      tool_bindings,
      mode_definitions,
      sub_agent_ids: subAgents,
    };
    try {
      const saved = editing
        ? await update.mutateAsync({ name, body })
        : await create.mutateAsync(body);
      if (photo) {
        await upload.mutateAsync({ name: saved.name, file: photo });
      }
      if (!editing) {
        setName("");
        setDescription("");
        setInstructions("");
        setModelRef(null);
        setErrors({});
        setTools([]);
        setMcpServers([]);
        setSubAgents([]);
        setPhoto(null);
      }
      onClose();
    } catch {
      notifications.show({
        message: editing ? "Failed to update agent" : "Failed to create agent",
        color: "red",
      });
    }
  }

  return (
    <Drawer
      opened={opened}
      onClose={onClose}
      title={editing ? "Edit agent" : "New agent"}
      size="lg"
    >
      <Section title="Identity">
        <FormField label="Name" required error={errors.name}>
          <TextInput
            placeholder="e.g. Reviewer"
            value={name}
            disabled={editing}
            onChange={(e) => setName(e.currentTarget.value)}
          />
        </FormField>
        <FormField label="Description">
          <TextInput
            placeholder="What is this agent for?"
            value={description}
            onChange={(e) => setDescription(e.currentTarget.value)}
          />
        </FormField>
        <FormField label="Instructions">
          <Textarea
            minRows={4}
            placeholder="System prompt and operating instructions"
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
            placeholder="Choose a model"
            data={modelOptions}
            value={modelRef}
            onChange={setModelRef}
            searchable
          />
        </FormField>
      </Section>

      <Section title="Capabilities">
        <AgentToolsEditor value={tools} onChange={setTools} />
        <AgentMcpEditor
          value={mcpServers}
          onChange={setMcpServers}
          error={errors.mcp}
        />
      </Section>

      <Section title="Behavior">
        <AgentModesEditor value={modes} onChange={setModes} />
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
        <Button onClick={onSubmit} loading={create.isPending || update.isPending}>
          {editing ? "Save agent" : "Create agent"}
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
