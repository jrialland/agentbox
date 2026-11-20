import type { Meta, StoryObj } from "@storybook/react-vite";
import {
  RiAddLine,
  RiDeleteBin6Line,
  RiMicLine,
  RiSettings3Line,
} from "@remixicon/react";

import { Icon } from "./Icon";
import { IconButton } from "./IconButton";

function IconsDemo() {
  return (
    <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
      <Icon as={RiAddLine} size={24} />
      <Icon as={RiSettings3Line} size={24} />
      <Icon as={RiMicLine} size={24} />
      <IconButton label="New session" icon={RiAddLine} />
      <IconButton label="Settings" icon={RiSettings3Line} />
      <IconButton
        label="Delete session"
        icon={RiDeleteBin6Line}
        color="red"
      />
    </div>
  );
}

const meta: Meta<typeof IconsDemo> = {
  title: "Icons/Overview",
  component: IconsDemo,
};

export default meta;
type Story = StoryObj<typeof IconsDemo>;
export const Default: Story = {};
