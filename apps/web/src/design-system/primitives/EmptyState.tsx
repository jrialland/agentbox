import type { RemixiconComponentType } from "@remixicon/react";
import type { ReactNode } from "react";

import { Icon } from "../icons/Icon";
import styles from "./primitives.module.css";

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: RemixiconComponentType;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className={styles.emptyState}>
      <Icon as={icon} size={32} />
      <h2>{title}</h2>
      <p>{description}</p>
      {action}
    </div>
  );
}
