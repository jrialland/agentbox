import { Badge, Button } from "@mantine/core";
import { useState } from "react";

import type { PlanItem } from "../api/endpoints";

const COLORS: Record<string, string> = {
  pending: "gray",
  in_progress: "blue",
  completed: "green",
};

export function PlanPanel({ items }: { items: PlanItem[] }) {
  const [open, setOpen] = useState(true);
  if (items.length === 0) return null;
  return (
    <div
      className="box"
      data-testid="plan-panel"
      style={{ marginBottom: "0.75rem" }}
    >
      <div className="is-flex is-justify-content-space-between is-align-items-center">
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
