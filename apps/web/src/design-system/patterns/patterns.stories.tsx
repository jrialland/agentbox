import type { Meta, StoryObj } from "@storybook/react-vite";
import { RiRobot2Line } from "@remixicon/react";

import { Button } from "../primitives/Button";
import { DashboardCard } from "./DashboardCard";
import { EmptyStatePanel } from "./EmptyStatePanel";
import { ListPage } from "./ListPage";

function PatternsDemo() {
  return (
    <div style={{ display: "grid", gap: 24 }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: 12,
        }}
      >
        <DashboardCard label="Projects" value={3} hint="configured" />
        <DashboardCard label="Sessions" value={12} hint="across projects" />
        <DashboardCard label="Agents" value={4} hint="available" />
      </div>
      <ListPage
        title="Agents"
        subtitle="4 configured agents"
        actions={<Button>New agent</Button>}
      >
        <EmptyStatePanel
          icon={RiRobot2Line}
          title="No agents"
          description="Create your first agent to start a session."
          action={<Button>Create agent</Button>}
        />
      </ListPage>
    </div>
  );
}

const meta: Meta<typeof PatternsDemo> = {
  title: "Patterns/Overview",
  component: PatternsDemo,
};

export default meta;
type Story = StoryObj<typeof PatternsDemo>;
export const Default: Story = {};
