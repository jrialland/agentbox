import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";

import { useAgentCard, useDeleteAgentCard, useSetAgentCard } from "../../api/queries";
import { Checkbox } from "../../design-system/forms/Checkbox";
import { FormField } from "../../design-system/forms/FormField";
import { MultiSelect } from "../../design-system/forms/MultiSelect";
import { TextInput } from "../../design-system/forms/TextInput";
import { Textarea } from "../../design-system/forms/Textarea";
import { Modal } from "../../design-system/overlays/Modal";
import { Button } from "../../design-system/primitives/Button";
import { Tabs } from "../../design-system/primitives/Tabs";
import { HelpTip } from "../../help/HelpTip";
import {
  EMPTY_A2A_CARD,
  mergeStructuredCard,
  parseCardJson,
  toStructuredCard,
  validateStructuredCard,
  type StructuredA2ACard,
} from "./a2aCard";
import { A2ASkillsEditor } from "./A2ASkillsEditor";

type RawCard = Record<string, unknown>;

export function AgentCardModal({
  name,
  onClose,
}: {
  name: string;
  onClose: () => void;
}) {
  const { data: card } = useAgentCard(name);
  const save = useSetAgentCard();
  const remove = useDeleteAgentCard();
  const [rawCard, setRawCard] = useState<RawCard | null>(null);
  const [structured, setStructuredState] =
    useState<StructuredA2ACard>(EMPTY_A2A_CARD);
  const [dirty, setDirty] = useState(false);

  function setStructured(next: StructuredA2ACard) {
    setDirty(true);
    setStructuredState(next);
  }
  const [jsonText, setJsonText] = useState("");
  const [tab, setTab] = useState<string | null>("structured");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [jsonError, setJsonError] = useState<string | null>(null);

  useEffect(() => {
    if (dirty) return;
    const raw =
      card ??
      ({ name, description: "", version: "1.0.0", skills: [] } as RawCard);
    setRawCard(raw);
    setStructuredState(toStructuredCard(raw, name));
    setJsonText(JSON.stringify(raw, null, 2));
    setDirty(false);
  }, [card, name, dirty]);

  function onJsonChange(text: string) {
    setJsonText(text);
    const parsed = parseCardJson(text);
    if (parsed.card) {
      setJsonError(null);
      setRawCard(parsed.card);
      setStructured(toStructuredCard(parsed.card, name));
    } else {
      setJsonError(parsed.error);
    }
  }

  async function onSave() {
    const parsed = tab === "json" ? parseCardJson(jsonText) : null;
    if (tab === "json" && !parsed?.card) {
      setJsonError(parsed?.error ?? "Invalid JSON.");
      return;
    }
    const nextErrors =
      tab === "structured" ? validateStructuredCard(structured) : {};
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0 || jsonError) return;
    const cardToSave =
      tab === "json" && parsed?.card
        ? parsed.card
        : mergeStructuredCard(rawCard, structured);
    try {
      await save.mutateAsync({ name, card: cardToSave });
      onClose();
    } catch {
      notifications.show({ message: "Failed to save agent card", color: "red" });
    }
  }

  return (
    <Modal opened onClose={onClose} title={`A2A card: ${name}`} size="lg">
      <Tabs
        value={tab}
        onChange={(value) => {
          setTab(value);
          if (value === "json") {
            setJsonText(
              JSON.stringify(
                rawCard ?? mergeStructuredCard(rawCard, structured),
                null,
                2,
              ),
            );
          } else {
            const parsed = parseCardJson(jsonText);
            if (parsed.card) {
              setRawCard(parsed.card);
              setStructured(toStructuredCard(parsed.card, name));
            }
          }
        }}
      >
        <Tabs.List>
          <Tabs.Tab value="structured">Structured</Tabs.Tab>
          <Tabs.Tab value="json">JSON</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="structured" pt="md">
          <FormField
            label="Agent card name"
            required
            error={errors.name}
            help={<HelpTip id="a2a.card" />}
          >
            <TextInput
              aria-label="Agent card name"
              value={structured.name}
              onChange={(event) =>
                setStructured({ ...structured, name: event.currentTarget.value })
              }
            />
          </FormField>
          <FormField label="Description">
            <Textarea
              aria-label="Agent card description"
              minRows={2}
              value={structured.description}
              onChange={(event) =>
                setStructured({
                  ...structured,
                  description: event.currentTarget.value,
                })
              }
            />
          </FormField>
          <FormField label="Version" required error={errors.version}>
            <TextInput
              aria-label="Agent card version"
              value={structured.version}
              onChange={(event) =>
                setStructured({
                  ...structured,
                  version: event.currentTarget.value,
                })
              }
            />
          </FormField>
          <div style={{ display: "grid", gap: 8, gridTemplateColumns: "1fr 1fr" }}>
            <FormField label="Provider organization">
              <TextInput
                value={structured.providerOrganization}
                onChange={(event) =>
                  setStructured({
                    ...structured,
                    providerOrganization: event.currentTarget.value,
                  })
                }
              />
            </FormField>
            <FormField label="Provider URL" error={errors.providerUrl}>
              <TextInput
                value={structured.providerUrl}
                onChange={(event) =>
                  setStructured({
                    ...structured,
                    providerUrl: event.currentTarget.value,
                  })
                }
              />
            </FormField>
          </div>
          <FormField label="Documentation URL" error={errors.documentationUrl}>
            <TextInput
              value={structured.documentationUrl}
              onChange={(event) =>
                setStructured({
                  ...structured,
                  documentationUrl: event.currentTarget.value,
                })
              }
            />
          </FormField>

          <h3>Capabilities</h3>
          <Checkbox
            label="Streaming"
            checked={structured.capabilities.streaming}
            onChange={(event) =>
              setStructured({
                ...structured,
                capabilities: {
                  ...structured.capabilities,
                  streaming: event.currentTarget.checked,
                },
              })
            }
          />
          <Checkbox
            label="Push notifications"
            checked={structured.capabilities.pushNotifications}
            onChange={(event) =>
              setStructured({
                ...structured,
                capabilities: {
                  ...structured.capabilities,
                  pushNotifications: event.currentTarget.checked,
                },
              })
            }
          />


          <FormField label="Default input modes">
            <MultiSelect
              searchable
              data={["text/plain", "application/json"]}
              value={structured.defaultInputModes}
              onChange={(value) =>
                setStructured({ ...structured, defaultInputModes: value })
              }
            />
          </FormField>
          <FormField label="Default output modes">
            <MultiSelect
              searchable
              data={["text/plain", "application/json"]}
              value={structured.defaultOutputModes}
              onChange={(value) =>
                setStructured({ ...structured, defaultOutputModes: value })
              }
            />
          </FormField>

          <h3>Skills</h3>
          <A2ASkillsEditor
            skills={structured.skills}
            error={errors.skills}
            onChange={(skills) => setStructured({ ...structured, skills })}
          />
        </Tabs.Panel>
        <Tabs.Panel value="json" pt="md">
          <Textarea
            aria-label="Agent card JSON"
            label="Agent card JSON"
            minRows={16}
            value={jsonText}
            onChange={(event) => onJsonChange(event.currentTarget.value)}
          />
          {jsonError && (
            <p role="alert" style={{ color: "var(--ab-danger)" }}>
              {jsonError}
            </p>
          )}
        </Tabs.Panel>
      </Tabs>

      <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
        <Button onClick={onSave} loading={save.isPending}>
          Save
        </Button>
        <Button
          variant="light"
          color="red"
          onClick={async () => {
            await remove.mutateAsync(name);
            onClose();
          }}
        >
          Remove
        </Button>
      </div>
    </Modal>
  );
}
