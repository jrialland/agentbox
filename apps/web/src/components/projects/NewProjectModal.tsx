import { Button, Modal, Textarea, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";

import type { Project } from "../../api/endpoints";
import { useCreateProject, useUpdateProject } from "../../api/queries";

function splitRoots(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

export function NewProjectModal({
  opened,
  onClose,
  project,
}: {
  opened: boolean;
  onClose: () => void;
  project?: Project | null;
}) {
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [roots, setRoots] = useState("");
  const create = useCreateProject();
  const update = useUpdateProject();
  const editing = !!project;
  const pending = create.isPending || update.isPending;

  useEffect(() => {
    if (!opened) return;
    setName(project?.name ?? "");
    setPath(project?.path ?? "");
    setRoots((project?.extra_roots ?? []).join("\n"));
  }, [opened, project]);

  async function submit() {
    const extra_roots = splitRoots(roots);
    if (project) {
      await update.mutateAsync({
        pid: project.id,
        body: { name, extra_roots },
      });
    } else {
      await create.mutateAsync({ name, path, extra_roots });
    }
    setName("");
    setPath("");
    setRoots("");
    onClose();
  }

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={editing ? "Project settings" : "New project"}
    >
      <TextInput
        label="Name"
        value={name}
        onChange={(e) => setName(e.currentTarget.value)}
      />
      {!editing && (
        <TextInput
          label="Path"
          value={path}
          onChange={(e) => setPath(e.currentTarget.value)}
        />
      )}
      <Textarea
        label="Additional allowed folders"
        description="One absolute path per line"
        minRows={3}
        value={roots}
        onChange={(e) => setRoots(e.currentTarget.value)}
      />
      <Button mt="md" onClick={submit} loading={pending}>
        {editing ? "Save" : "Create"}
      </Button>
    </Modal>
  );
}
