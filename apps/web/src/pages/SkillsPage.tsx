import { notifications } from "@mantine/notifications";
import { RiBookOpenLine, RiDeleteBin6Line, RiSettings3Line } from "@remixicon/react";
import { useState } from "react";

import { fetchSkill } from "../api/endpoints";
import { useDeleteSkill, useSaveSkill, useSkills } from "../api/queries";
import { DataTable } from "../design-system/data/DataTable";
import { FormField } from "../design-system/forms/FormField";
import { TextInput } from "../design-system/forms/TextInput";
import { Textarea } from "../design-system/forms/Textarea";
import { IconButton } from "../design-system/icons/IconButton";
import { ConfirmDialog } from "../design-system/overlays/ConfirmDialog";
import { ErrorState } from "../design-system/patterns/ErrorState";
import { GuidedEmptyState } from "../design-system/patterns/GuidedEmptyState";
import { ListPage } from "../design-system/patterns/ListPage";
import { Button } from "../design-system/primitives/Button";
import { Panel } from "../design-system/primitives/Panel";
import { StatusChip } from "../design-system/primitives/StatusChip";

type SkillRow = { name: string; description: string; scope: string };

export function SkillsPage() {
  const { data: skills, error, refetch } = useSkills();
  const save = useSaveSkill();
  const del = useDeleteSkill();
  const [editing, setEditing] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [body, setBody] = useState("");
  const [skillToDelete, setSkillToDelete] = useState<string | null>(null);

  function reset() {
    setEditing(null);
    setName("");
    setDescription("");
    setBody("");
  }

  async function onEdit(skill: SkillRow) {
    try {
      const detail = await fetchSkill(skill.name);
      setEditing(skill.name);
      setName(skill.name);
      setDescription(detail.description);
      setBody(detail.body);
    } catch {
      notifications.show({ message: "Failed to load skill", color: "red" });
    }
  }

  async function onSave() {
    try {
      await save.mutateAsync({ name, body: { description, body } });
      reset();
    } catch {
      notifications.show({
        message: "Invalid skill (check the name and description)",
        color: "red",
      });
    }
  }

  return (
    <ListPage
      title="Skills"
      subtitle="Reusable instruction packs available from the composer"
    >
      <Panel>
        <Panel.Header>{editing ? `Edit skill · ${editing}` : "New skill"}</Panel.Header>
        <Panel.Body>
          <div style={{ display: "grid", gap: 12, maxWidth: 720 }}>
            <FormField label="Name" required>
              <TextInput
                id="skill-name"
                value={name}
                disabled={editing !== null}
                onChange={(e) => setName(e.currentTarget.value)}
              />
            </FormField>
            <FormField label="Description" required>
              <Textarea
                minRows={2}
                value={description}
                onChange={(e) => setDescription(e.currentTarget.value)}
              />
            </FormField>
            <FormField label="Body (Markdown)">
              <Textarea
                minRows={6}
                value={body}
                onChange={(e) => setBody(e.currentTarget.value)}
              />
            </FormField>
            <div style={{ display: "flex", gap: 8 }}>
              <Button onClick={onSave} loading={save.isPending}>
                {editing ? "Save skill" : "Create skill"}
              </Button>
              {editing && (
                <Button variant="light" onClick={reset}>
                  Cancel
                </Button>
              )}
            </div>
          </div>
        </Panel.Body>
      </Panel>

      {error ? (
        <ErrorState
          title="Could not load skills"
          message={error.message}
          onRetry={() => void refetch()}
        />
      ) : (skills ?? []).length === 0 ? (
        <GuidedEmptyState
          icon={RiBookOpenLine}
          title="No skills yet"
          description="Create a reusable instruction pack and invoke it from chat with /."
          helpId="skills.overview"
          action={
            <Button onClick={() => document.getElementById("skill-name")?.focus()}>
              Create your first skill
            </Button>
          }
        />
      ) : (
      <DataTable<SkillRow>
        rowKey={(skill) => skill.name}
        rows={(skills ?? []) as SkillRow[]}
        columns={[
          { key: "name", header: "Name", render: (skill) => skill.name },
          {
            key: "description",
            header: "Description",
            render: (skill) => skill.description,
          },
          {
            key: "scope",
            header: "Scope",
            render: (skill) => (
              <StatusChip tone={skill.scope === "user" ? "success" : "neutral"}>
                {skill.scope}
              </StatusChip>
            ),
          },
          {
            key: "actions",
            header: "Actions",
            render: (skill) =>
              skill.scope === "user" ? (
                <div style={{ display: "flex", gap: 2 }}>
                  <IconButton
                    label="Edit"
                    icon={RiSettings3Line}
                    size={16}
                    onClick={() => onEdit(skill)}
                  />
                  <IconButton
                    label="Delete"
                    icon={RiDeleteBin6Line}
                    size={16}
                    color="red"
                    onClick={() => setSkillToDelete(skill.name)}
                  />
                </div>
              ) : null,
          },
        ]}
      />
      )}
      <ConfirmDialog
        opened={skillToDelete !== null}
        title="Delete skill?"
        description={`Delete "${skillToDelete ?? ""}" permanently? This cannot be undone.`}
        confirmLabel="Delete"
        danger
        onConfirm={async () => {
          if (!skillToDelete) return;
          await del.mutateAsync(skillToDelete);
          setSkillToDelete(null);
        }}
        onClose={() => setSkillToDelete(null)}
      />
    </ListPage>
  );
}

