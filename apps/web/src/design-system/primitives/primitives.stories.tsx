import type { Meta, StoryObj } from "@storybook/react-vite";
import { RiRobot2Line } from "@remixicon/react";

import { Button } from "./Button";
import { EmptyState } from "./EmptyState";
import { PageHeader } from "./PageHeader";
import { Panel } from "./Panel";
import { StatusChip } from "./StatusChip";

function PrimitivesDemo() {
  return (
    <div style={{ display: "grid", gap: 24 }}>
      <PageHeader
        title="Agents"
        subtitle="2 configured agents"
        actions={<Button leftSection={<span>+</span>}>New agent</Button>}
      />
      <Panel>
        <Panel.Header>Projects</Panel.Header>
        <Panel.Body>Panel body</Panel.Body>
      </Panel>
      <div style={{ display: "flex", gap: 8 }}>
        <StatusChip tone="success">active</StatusChip>
        <StatusChip tone="warning">degraded</StatusChip>
        <StatusChip tone="danger">error</StatusChip>
      </div>
      <EmptyState
        icon={RiRobot2Line}
        title="No agents"
        description="Create your first agent."
        action={<Button>Create agent</Button>}
      />
    </div>
  );
}

const meta: Meta<typeof PrimitivesDemo> = {
  title: "Primitives/Surfaces",
  component: PrimitivesDemo,
};

export default meta;
type Story = StoryObj<typeof PrimitivesDemo>;
export const Default: Story = {};
