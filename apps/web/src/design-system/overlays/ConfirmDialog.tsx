import { Button, Group, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";

import { Modal } from "./Modal";

export function ConfirmDialog({
  opened,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger,
  requireText,
  onConfirm,
  onClose,
}: {
  opened: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  requireText?: string;
  onConfirm: () => Promise<void> | void;
  onClose: () => void;
}) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (opened) {
      setTyped("");
      setError(null);
    }
  }, [opened]);

  const matches = !requireText || typed.trim() === requireText.trim();

  async function confirm() {
    if (!matches) return;
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal opened={opened} onClose={onClose} title={title}>
      <p>{description}</p>
      {requireText && (
        <TextInput
          label={`Type ${requireText} to confirm`}
          value={typed}
          onChange={(event) => setTyped(event.currentTarget.value)}
        />
      )}
      {error && <p role="alert">{error}</p>}
      <Group justify="flex-end" mt="md">
        <Button variant="light" onClick={onClose}>
          {cancelLabel}
        </Button>
        <Button
          color={danger ? "danger" : "phosphor"}
          disabled={!matches}
          loading={busy}
          onClick={confirm}
        >
          {confirmLabel}
        </Button>
      </Group>
    </Modal>
  );
}
