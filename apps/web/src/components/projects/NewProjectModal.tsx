import { Button, Modal } from "@mantine/core";
import { useEffect, useState } from "react";

import type { Project } from "../../api/endpoints";
import { ApiError } from "../../api/errors";
import { useCreateProject, useUpdateProject } from "../../api/queries";
import { FormField } from "../../design-system/forms/FormField";
import { Textarea } from "../../design-system/forms/Textarea";
import { TextInput } from "../../design-system/forms/TextInput";
import { firstFieldError, isAbsolutePath, requiredText } from "../../lib/validation";

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
  const [formError, setFormError] = useState<string | null>(null);
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
    setFormError(null);
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
    setFormError(null);
    const trimmedName = name.trim();
    const extra_roots = splitRoots(roots);
    try {
      if (project) {
        await update.mutateAsync({
          pid: project.id,
          body: { name: trimmedName, extra_roots },
        });
      } else {
        await create.mutateAsync({ name: trimmedName, path, extra_roots });
      }
    } catch (caught) {
      if (caught instanceof ApiError) {
        const mapped: Record<string, string> = {};
        const nameError = firstFieldError(caught.fields, "name");
        if (nameError) mapped.name = nameError;
        const pathError = firstFieldError(caught.fields, "path");
        if (pathError) mapped.path = pathError;
        const rootsError = firstFieldError(caught.fields, "extra_roots");
        if (rootsError) mapped.roots = rootsError;
        if (Object.keys(mapped).length > 0) {
          setErrors(mapped);
        } else {
          setFormError(caught.detail);
        }
      } else {
        setFormError(caught instanceof Error ? caught.message : "Request failed.");
      }
      return;
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
      {formError && <p role="alert">{formError}</p>}
      <Button mt="md" onClick={submit} loading={pending}>
        {editing ? "Save" : "Create"}
      </Button>
    </Modal>
  );
}
