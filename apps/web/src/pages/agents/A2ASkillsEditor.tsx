import { RiArrowDownLine, RiArrowUpLine, RiDeleteBin6Line } from "@remixicon/react";

import { TextInput } from "../../design-system/forms/TextInput";
import { Textarea } from "../../design-system/forms/Textarea";
import { IconButton } from "../../design-system/icons/IconButton";
import { Button } from "../../design-system/primitives/Button";
import type { A2ASkill } from "./a2aCard";

export function A2ASkillsEditor({
  skills,
  onChange,
  error,
}: {
  skills: A2ASkill[];
  onChange: (skills: A2ASkill[]) => void;
  error?: string;
}) {
  function update(index: number, patch: Partial<A2ASkill>) {
    onChange(skills.map((skill, i) => (i === index ? { ...skill, ...patch } : skill)));
  }

  function move(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= skills.length) return;
    const next = [...skills];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  }

  return (
    <div style={{ display: "grid", gap: 12 }}>
      {skills.map((skill, index) => (
        <div
          key={`${skill.id}-${index}`}
          style={{
            border: "1px solid var(--ab-border)",
            borderRadius: 4,
            display: "grid",
            gap: 8,
            padding: 12,
          }}
        >
          <div style={{ display: "grid", gap: 8, gridTemplateColumns: "1fr 2fr" }}>
            <TextInput
              aria-label={`Skill ${index + 1} id`}
              label="Skill id"
              value={skill.id}
              onChange={(event) => update(index, { id: event.currentTarget.value })}
            />
            <TextInput
              aria-label={`Skill ${index + 1} name`}
              label="Name"
              value={skill.name}
              onChange={(event) => update(index, { name: event.currentTarget.value })}
            />
          </div>
          <Textarea
            aria-label={`Skill ${index + 1} description`}
            label="Description"
            minRows={2}
            value={skill.description}
            onChange={(event) =>
              update(index, { description: event.currentTarget.value })
            }
          />
          <TextInput
            aria-label={`Skill ${index + 1} tags`}
            label="Tags"
            description="Comma-separated"
            value={skill.tags.join(", ")}
            onChange={(event) =>
              update(index, {
                tags: event.currentTarget.value
                  .split(",")
                  .map((tag) => tag.trim())
                  .filter(Boolean),
              })
            }
          />
          <Textarea
            aria-label={`Skill ${index + 1} examples`}
            label="Examples"
            description="One example per line"
            minRows={2}
            value={skill.examples.join("\n")}
            onChange={(event) =>
              update(index, {
                examples: event.currentTarget.value
                  .split("\n")
                  .map((example) => example.trim())
                  .filter(Boolean),
              })
            }
          />
          <div style={{ display: "flex", gap: 4 }}>
            <IconButton
              label={`Move skill ${index + 1} up`}
              icon={RiArrowUpLine}
              size={16}
              onClick={() => move(index, -1)}
            />
            <IconButton
              label={`Move skill ${index + 1} down`}
              icon={RiArrowDownLine}
              size={16}
              onClick={() => move(index, 1)}
            />
            <IconButton
              label={`Remove skill ${index + 1}`}
              icon={RiDeleteBin6Line}
              size={16}
              color="red"
              onClick={() => onChange(skills.filter((_, i) => i !== index))}
            />
          </div>
        </div>
      ))}
      {error && (
        <span role="alert" style={{ color: "var(--ab-danger)" }}>
          {error}
        </span>
      )}
      <Button
        variant="light"
        onClick={() =>
          onChange([
            ...skills,
            { id: "", name: "", description: "", tags: [], examples: [] },
          ])
        }
      >
        Add skill
      </Button>
    </div>
  );
}
