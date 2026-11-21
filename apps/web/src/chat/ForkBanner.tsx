import { RiCloseLine } from "@remixicon/react";

import { IconButton } from "../design-system/icons/IconButton";
import { StatusChip } from "../design-system/primitives/StatusChip";
import styles from "./chat.module.css";

export function ForkBanner({ onCancel }: { onCancel: () => void }) {
  return (
    <div className={styles.forkBanner} role="status">
      <StatusChip tone="warning">edit</StatusChip>
      <span>Editing from this turn - sending creates a new branch</span>
      <IconButton
        label="Cancel edit"
        icon={RiCloseLine}
        size={16}
        onClick={onCancel}
      />
    </div>
  );
}
