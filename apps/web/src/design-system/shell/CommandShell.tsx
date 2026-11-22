import { useMediaQuery } from "@mantine/hooks";
import {
  RiBookOpenLine,
  RiHome5Line,
  RiKey2Line,
  RiPlugLine,
  RiRobot2Line,
  RiServerLine,
  RiShieldUserLine,
} from "@remixicon/react";
import type { RemixiconComponentType } from "@remixicon/react";
import { useState } from "react";
import { Outlet, useNavigate } from "react-router-dom";

import { useAuthStore } from "../../store/auth";
import { AppRail } from "../navigation/AppRail";
import { MobileTopBar } from "../navigation/MobileTopBar";
import { ProjectPanel } from "../navigation/ProjectPanel";
import { ProjectSheet } from "../navigation/ProjectSheet";
import { RailItem } from "../navigation/RailItem";
import type { NavItem } from "../navigation/types";
import { UserMenu } from "../navigation/UserMenu";
import { ThemeToggle } from "../theme/ThemeToggle";
import { Workspace } from "./Workspace";
import styles from "./shell.module.css";

type ShellItem = NavItem & {
  permission?: string | string[];
};

const items: ShellItem[] = [
  { to: "/", label: "Home", icon: RiHome5Line, end: true },
  { to: "/agents", label: "Agents", icon: RiRobot2Line },
  { to: "/providers", label: "Providers", icon: RiServerLine },
  { to: "/skills", label: "Skills", icon: RiBookOpenLine },
  {
    to: "/plugins",
    label: "Plugins",
    icon: RiPlugLine,
    permission: "plugins:read",
  },
  {
    to: "/api-keys",
    label: "API keys",
    icon: RiKey2Line,
    permission: "api_keys:manage",
  },
  {
    to: "/admin",
    label: "Admin",
    icon: RiShieldUserLine,
    permission: ["roles:manage", "users:manage"],
  },
];

function allowed(permissions: string[], required?: string | string[]) {
  if (!required) return true;
  const list = Array.isArray(required) ? required : [required];
  return list.some((permission) => permissions.includes(permission));
}

export function CommandShell() {
  const user = useAuthStore((state) => state.user);
  const clear = useAuthStore((state) => state.clear);
  const navigate = useNavigate();
  const isMobile = useMediaQuery("(max-width: 1099px)") ?? false;
  const isPhone = useMediaQuery("(max-width: 767px)") ?? false;
  const [projectSheet, setProjectSheet] = useState(false);
  const permissions = user?.permissions ?? [];
  const visible = items.filter((item) => allowed(permissions, item.permission));
  const navItems: NavItem[] = visible.map(({ permission: _permission, ...item }) => item);

  function logout() {
    clear();
    navigate("/login");
  }

  if (isMobile) {
    return (
      <div className={styles.mobileShell}>
        <MobileTopBar
          items={navItems}
          onOpenProjects={() => setProjectSheet(true)}
          onLogout={logout}
          username={user?.username ?? "operator"}
        />
        <div className={isPhone ? styles.mobileBodyPhone : styles.mobileBody}>
          {!isPhone && (
            <aside className={styles.projectPane} aria-label="Projects">
              <ProjectPanel />
            </aside>
          )}
          <Workspace>
            <Outlet />
          </Workspace>
        </div>
        {isPhone && (
          <ProjectSheet
            opened={projectSheet}
            onClose={() => setProjectSheet(false)}
          />
        )}
      </div>
    );
  }

  return (
    <div className={styles.shell}>
      <AppRail
        footer={
          <>
            <ThemeToggle />
            <UserMenu
              username={user?.username ?? "operator"}
              onLogout={logout}
            />
          </>
        }
      >
        {visible.map((item) => (
          <RailItem
            key={item.to}
            to={item.to}
            label={item.label}
            icon={item.icon}
            end={item.end}
          />
        ))}
      </AppRail>
      <aside className={styles.projectPane} aria-label="Projects">
        <ProjectPanel />
      </aside>
      <Workspace>
        <Outlet />
      </Workspace>
    </div>
  );
}
