import {
  RiBookOpenLine,
  RiHome5Line,
  RiKey2Line,
  RiRobot2Line,
  RiServerLine,
  RiShieldUserLine,
} from "@remixicon/react";
import type { RemixiconComponentType } from "@remixicon/react";
import { Outlet, useNavigate } from "react-router-dom";

import { useAuthStore } from "../../store/auth";
import { AppRail } from "../navigation/AppRail";
import { ProjectPanel } from "../navigation/ProjectPanel";
import { RailItem } from "../navigation/RailItem";
import { UserMenu } from "../navigation/UserMenu";
import { ThemeToggle } from "../theme/ThemeToggle";
import { Workspace } from "./Workspace";
import styles from "./shell.module.css";

type NavItem = {
  to: string;
  label: string;
  icon: RemixiconComponentType;
  end?: boolean;
  permission?: string | string[];
};

const items: NavItem[] = [
  { to: "/", label: "Home", icon: RiHome5Line, end: true },
  { to: "/agents", label: "Agents", icon: RiRobot2Line },
  { to: "/providers", label: "Providers", icon: RiServerLine },
  { to: "/skills", label: "Skills", icon: RiBookOpenLine },
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
  const permissions = user?.permissions ?? [];
  const visible = items.filter((item) => allowed(permissions, item.permission));

  function logout() {
    clear();
    navigate("/login");
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
