import { Button, Modal, TextInput } from "@mantine/core";
import { useState } from "react";

import { useCreateProject } from "../../api/queries";

export function NewProjectModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const create = useCreateProject();

  async function submit() {
    await create.mutateAsync({ name, path });
    setName("");
    setPath("");
    onClose();
  }

  return (
    <Modal opened={opened} onClose={onClose} title="New project">
      <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
      <TextInput label="Path" value={path} onChange={(e) => setPath(e.currentTarget.value)} />
      <Button mt="md" onClick={submit} loading={create.isPending}>
        Create
      </Button>
    </Modal>
  );
}
