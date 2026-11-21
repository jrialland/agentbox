import type { Meta, StoryObj } from "@storybook/react-vite";

import { ErrorState } from "./ErrorState";

const meta: Meta<typeof ErrorState> = {
  title: "Patterns/ErrorStates",
  component: ErrorState,
};
export default meta;
type Story = StoryObj<typeof ErrorState>;

export const Error: Story = {
  args: {
    title: "Could not load projects",
    message: "The server could not be reached. Try again.",
    onRetry: () => {},
  },
};
