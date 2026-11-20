import { Button, Group } from "@mantine/core";

import { Modal } from "./Modal";

export function ConfirmDialog({
  opened,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger,
  onConfirm,
  onClose,
}: {
  opened: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Modal opened={opened} onClose={onClose} title={title}>
      <p>{description}</p>
      <Group justify="flex-end" mt="md">
        <Button variant="light" onClick={onClose}>
          {cancelLabel}
        </Button>
        <Button color={danger ? "danger" : "phosphor"} onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </Group>
    </Modal>
  );
}
