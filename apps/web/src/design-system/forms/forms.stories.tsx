import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";

import { Button } from "../primitives/Button";
import { Checkbox } from "./Checkbox";
import { FileDropzone } from "./FileDropzone";
import { FormActions } from "./FormActions";
import { FormField } from "./FormField";
import { PasswordInput } from "./PasswordInput";
import { Select } from "./Select";
import { TextInput } from "./TextInput";
import { Textarea } from "./Textarea";

function FormsDemo() {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<string | null>("generic");
  const [active, setActive] = useState(true);

  return (
    <form style={{ maxWidth: 480 }}>
      <FormField label="Name" description="A short display name" required>
        <TextInput value={name} onChange={(e) => setName(e.currentTarget.value)} />
      </FormField>
      <FormField label="Kind">
        <Select
          data={["generic", "deepseek", "ollama"]}
          value={kind}
          onChange={setKind}
        />
      </FormField>
      <FormField label="Instructions">
        <Textarea minRows={3} placeholder="You are a helpful assistant." />
      </FormField>
      <FormField label="API key">
        <PasswordInput placeholder="sk-..." />
      </FormField>
      <Checkbox
        label="Enable agent mode"
        checked={active}
        onChange={(e) => setActive(e.currentTarget.checked)}
      />
      <FileDropzone onFiles={() => {}} />
      <FormActions>
        <Button variant="light">Cancel</Button>
        <Button type="submit">Save</Button>
      </FormActions>
    </form>
  );
}

const meta: Meta<typeof FormsDemo> = {
  title: "Forms/Overview",
  component: FormsDemo,
};

export default meta;
type Story = StoryObj<typeof FormsDemo>;
export const Default: Story = {};
