import { RiFolderLine } from "@remixicon/react";

import { IconButton } from "../icons/IconButton";
import styles from "./navigation.module.css";
import { MobileNav } from "./MobileNav";
import type { NavItem } from "./types";

export function MobileTopBar({
  items,
  onOpenProjects,
  onLogout,
  username,
}: {
  items: NavItem[];
  onOpenProjects: () => void;
  onLogout: () => void;
  username: string;
}) {
  return (
    <header className={styles.mobileTopBar}>
      <div className={styles.mobileTopRow}>
        <span className={styles.mobileBrand}>[AGENTBOX]▮</span>
        <div className={styles.mobileActions}>
          <IconButton
            label="Projects"
            icon={RiFolderLine}
            size={18}
            onClick={onOpenProjects}
          />
          <button
            type="button"
            className={styles.mobileUser}
            onClick={onLogout}
            aria-label={`Logout ${username}`}
          >
            {username.slice(0, 1).toUpperCase()}
          </button>
        </div>
      </div>
      <MobileNav items={items} />
    </header>
  );
}
