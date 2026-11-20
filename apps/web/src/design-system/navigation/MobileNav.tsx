import { NavLink } from "react-router-dom";

import { Icon } from "../icons/Icon";
import styles from "./navigation.module.css";
import type { NavItem } from "./types";

export function MobileNav({ items }: { items: NavItem[] }) {
  return (
    <nav className={styles.mobileNav} aria-label="Primary navigation">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={styles.mobileNavItem}
        >
          <Icon as={item.icon} size={18} />
          <span>{item.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
