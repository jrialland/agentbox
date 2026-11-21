import { Button, Modal } from "@mantine/core";
import { useEffect, useState } from "react";

import type { Project } from "../../api/endpoints";
import { useCreateProject, useUpdateProject } from "../../api/queries";
import { FormField } from "../../design-system/forms/FormField";
import { Textarea } from "../../design-system/forms/Textarea";
import { TextInput } from "../../design-system/forms/TextInput";
import { isAbsolutePath, requiredText } from "../../lib/validation";

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
  const [errors, setErrors] = useState<Record<string, string>>({});
  const create = useCreateProject();
  const update = useUpdateProject();
  const editing = !!project;
  const pending = create.isPending || update.isPending;

  useEffect(() => {
    if (!opened) return;
    setName(project?.name ?? "");
    setPath(project?.path ?? "");
    setRoots((project?.extra_roots ?? []).join("\n"));
    setErrors({});
  }, [opened, project]);

  function validate() {
    const next: Record<string, string> = {};
    const nameError = requiredText(name, "Name");
    if (nameError) next.name = nameError;
    if (!editing) {
      const pathError = requiredText(path, "Path");
      if (pathError) next.path = pathError;
    }
    const rootsError = splitRoots(roots).find((root) => !isAbsolutePath(root));
    if (rootsError) next.roots = "Additional folders must be absolute paths.";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function submit() {
    if (!validate()) return;
    const trimmedName = name.trim();
    const extra_roots = splitRoots(roots);
    if (project) {
      await update.mutateAsync({
        pid: project.id,
        body: { name: trimmedName, extra_roots },
      });
    } else {
      await create.mutateAsync({ name: trimmedName, path, extra_roots });
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
      <FormField label="Name" required error={errors.name}>
        <TextInput
          aria-label="Name"
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
        />
      </FormField>
      {!editing && (
        <FormField label="Path" required error={errors.path}>
          <TextInput
            aria-label="Path"
            value={path}
            onChange={(e) => setPath(e.currentTarget.value)}
          />
        </FormField>
      )}
      <FormField
        label="Additional allowed folders"
        description="One absolute path per line"
        error={errors.roots}
      >
        <Textarea
          aria-label="Additional allowed folders"
          minRows={3}
          value={roots}
          onChange={(e) => setRoots(e.currentTarget.value)}
        />
      </FormField>
      <Button mt="md" onClick={submit} loading={pending}>
        {editing ? "Save" : "Create"}
      </Button>
    </Modal>
  );
}
