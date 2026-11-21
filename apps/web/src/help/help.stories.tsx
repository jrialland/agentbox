import type { Meta, StoryObj } from "@storybook/react-vite";

import { HelpDrawer } from "./HelpDrawer";
import { HelpProvider } from "./HelpProvider";

const meta: Meta = { title: "Help/States" };
export default meta;

export const Overview: StoryObj = {
  render: () => (
    <HelpProvider>
      <HelpDrawer active="provider.kind" onClose={() => {}} />
    </HelpProvider>
  ),
};
