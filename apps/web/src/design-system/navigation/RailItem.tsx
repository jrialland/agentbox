import { NavLink } from "react-router-dom";

import { Icon } from "../icons/Icon";
import styles from "./navigation.module.css";
import type { NavItem } from "./types";

export function RailItem({ to, label, icon, end }: NavItem) {
  return (
    <NavLink
      to={to}
      end={end}
      className={styles.railItem}
      aria-label={label}
      title={label}
    >
      {({ isActive }) => (
        <>
          <Icon as={icon} size={20} />
          <span className={styles.railLabel}>{label}</span>
          {isActive && <span className={styles.railActive} aria-hidden="true" />}
        </>
      )}
    </NavLink>
  );
}
