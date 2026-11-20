import type { Meta, StoryObj } from "@storybook/react-vite";
import {
  RiBookOpenLine,
  RiHome5Line,
  RiKey2Line,
  RiRobot2Line,
  RiServerLine,
  RiShieldUserLine,
} from "@remixicon/react";
import { MemoryRouter } from "react-router-dom";

import { AppRail } from "./AppRail";
import { Breadcrumbs } from "./Breadcrumbs";
import { MobileNav } from "./MobileNav";
import { RailItem } from "./RailItem";
import { UserMenu } from "./UserMenu";
import type { NavItem } from "./types";

const items: NavItem[] = [
  { to: "/", label: "Home", icon: RiHome5Line, end: true },
  { to: "/agents", label: "Agents", icon: RiRobot2Line },
  { to: "/providers", label: "Providers", icon: RiServerLine },
  { to: "/skills", label: "Skills", icon: RiBookOpenLine },
  { to: "/api-keys", label: "API keys", icon: RiKey2Line },
  { to: "/admin", label: "Admin", icon: RiShieldUserLine },
];

function NavigationDemo() {
  return (
    <MemoryRouter initialEntries={["/agents"]}>
      <div style={{ display: "flex", gap: 24 }}>
        <AppRail footer={<UserMenu username="admin" onLogout={() => {}} />}>
          {items.map((item) => (
            <RailItem key={item.to} {...item} />
          ))}
        </AppRail>
        <div style={{ display: "grid", gap: 16, flex: 1 }}>
          <Breadcrumbs items={[{ label: "Home", to: "/" }, { label: "Agents" }]} />
          <MobileNav items={items} />
        </div>
      </div>
    </MemoryRouter>
  );
}

const meta: Meta<typeof NavigationDemo> = {
  title: "Navigation/Overview",
  component: NavigationDemo,
};

export default meta;
type Story = StoryObj<typeof NavigationDemo>;
export const Default: Story = {};
