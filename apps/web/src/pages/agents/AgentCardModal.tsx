import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { useAgentCard, useDeleteAgentCard, useSetAgentCard } from "../../api/queries";
import { Textarea } from "../../design-system/forms/Textarea";
import { Modal } from "../../design-system/overlays/Modal";
import { Button } from "../../design-system/primitives/Button";

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
      <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
        <Button onClick={onSave}>Save</Button>
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
