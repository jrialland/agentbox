import { Modal as MantineModal, type ModalProps } from "@mantine/core";

export function Modal(props: ModalProps) {
  return <MantineModal radius="md" centered {...props} />;
}
