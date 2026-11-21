import type { Meta, StoryObj } from "@storybook/react-vite";

import { FormField } from "./FormField";
import { TextInput } from "./TextInput";

function ValidationDemo() {
  return (
    <FormField label="Project name" required error="Name is required.">
      <TextInput value="" onChange={() => {}} />
    </FormField>
  );
}

const meta: Meta<typeof ValidationDemo> = {
  title: "Forms/Validation",
  component: ValidationDemo,
};
export default meta;
type Story = StoryObj<typeof ValidationDemo>;

export const Errors: Story = {};
