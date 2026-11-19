import { Button, Table, Textarea, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { fetchSkill } from "../api/endpoints";
import { useDeleteSkill, useSaveSkill, useSkills } from "../api/queries";

export function SkillsPage() {
  const { data: skills } = useSkills();
  const save = useSaveSkill();
  const del = useDeleteSkill();
  const [editing, setEditing] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [body, setBody] = useState("");

  function reset() {
    setEditing(null);
    setName("");
    setDescription("");
    setBody("");
  }

  async function onEdit(skill: { name: string; description: string }) {
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
    <div>
      <h1 className="title">Skills</h1>
      <div className="box">
        <TextInput
          label="Name"
          value={name}
          disabled={editing !== null}
          onChange={(e) => setName(e.currentTarget.value)}
        />
        <Textarea
          label="Description"
          value={description}
          onChange={(e) => setDescription(e.currentTarget.value)}
        />
        <Textarea
          label="Body (Markdown)"
          minRows={6}
          value={body}
          onChange={(e) => setBody(e.currentTarget.value)}
        />
        <Button mt="md" onClick={onSave} loading={save.isPending}>
          {editing ? "Save skill" : "Create skill"}
        </Button>
        {editing && (
          <Button mt="md" ml="sm" variant="light" onClick={reset}>
            Cancel
          </Button>
        )}
      </div>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Name</Table.Th>
            <Table.Th>Description</Table.Th>
            <Table.Th>Scope</Table.Th>
            <Table.Th>Actions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {(skills ?? []).map((s) => (
            <Table.Tr key={s.name}>
              <Table.Td>{s.name}</Table.Td>
              <Table.Td>{s.description}</Table.Td>
              <Table.Td>{s.scope}</Table.Td>
              <Table.Td>
                {s.scope === "user" && (
                  <>
                    <Button size="xs" onClick={() => onEdit(s)}>
                      Edit
                    </Button>{" "}
                    <Button
                      size="xs"
                      color="red"
                      onClick={() => del.mutateAsync(s.name)}
                    >
                      Delete
                    </Button>
                  </>
                )}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}
