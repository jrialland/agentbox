import type { Meta, StoryObj } from "@storybook/react-vite";

import { CodeBlock } from "./CodeBlock";
import { CopyButton } from "./CopyButton";
import { Kbd } from "./Kbd";
import { Skeleton } from "./Skeleton";
import { Spinner } from "./Spinner";
import { Tabs } from "./Tabs";

function FeedbackDemo() {
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <Spinner label="Thinking" />
        <span>Thinking…</span>
      </div>
      <Skeleton width={280} height={20} />
      <CodeBlock code={'const answer = 42;\nconsole.log(answer);'} language="ts" />
      <CopyButton value="hello" />
      <div style={{ display: "flex", gap: 4 }}>
        <Kbd>Ctrl</Kbd>
        <Kbd>K</Kbd>
      </div>
      <Tabs defaultValue="one">
        <Tabs.List>
          <Tabs.Tab value="one">One</Tabs.Tab>
          <Tabs.Tab value="two">Two</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="one">First panel</Tabs.Panel>
        <Tabs.Panel value="two">Second panel</Tabs.Panel>
      </Tabs>
    </div>
  );
}

const meta: Meta<typeof FeedbackDemo> = {
  title: "Primitives/Feedback",
  component: FeedbackDemo,
};

export default meta;
type Story = StoryObj<typeof FeedbackDemo>;
export const Default: Story = {};
