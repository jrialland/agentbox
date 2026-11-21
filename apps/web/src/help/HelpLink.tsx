import type { ReactNode } from "react";

import { useHelp } from "./HelpProvider";
import styles from "./help.module.css";
import type { HelpId } from "./types";

export function HelpLink({ id, children }: { id: HelpId; children: ReactNode }) {
  const { openHelp } = useHelp();
  return (
    <button
      type="button"
      className={styles.helpLink}
      onClick={() => openHelp(id)}
    >
      {children}
    </button>
  );
}
