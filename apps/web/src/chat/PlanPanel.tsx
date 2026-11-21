import { Badge, Button } from "@mantine/core";
import { useState } from "react";

import type { PlanItem } from "../api/endpoints";
import styles from "./chat.module.css";

const COLORS: Record<string, string> = {
  pending: "gray",
  in_progress: "blue",
  completed: "green",
};

export function PlanPanel({ items }: { items: PlanItem[] }) {
  const [open, setOpen] = useState(true);
  if (items.length === 0) return null;
  return (
    <div className={styles.notice} data-testid="plan-panel">
      <div className={styles.noticeHead}>
        <strong>Plan ({items.length})</strong>
        <Button
          size="compact-xs"
          variant="subtle"
          onClick={() => setOpen((value) => !value)}
        >
          {open ? "Hide" : "Show"}
        </Button>
      </div>
      {open && (
        <ul>
          {items.map((item) => (
            <li key={item.id}>
              <Badge color={COLORS[item.status] ?? "gray"} mr={6}>
                {item.status}
              </Badge>
              {item.content}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

