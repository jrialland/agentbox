import { Button } from "@mantine/core";
import { useState } from "react";

import { MarkdownBlock } from "./MarkdownBlock";

export function SummaryNotice({ content }: { content: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div
      className="box"
      data-testid="summary-notice"
      style={{ marginBottom: "0.75rem" }}
    >
      <div className="is-flex is-justify-content-space-between is-align-items-center">
        <strong>Earlier conversation summarized</strong>
        <Button
          size="compact-xs"
          variant="subtle"
          onClick={() => setOpen((value) => !value)}
        >
          {open ? "Hide" : "Show"}
        </Button>
      </div>
      {open && <MarkdownBlock content={content} />}
    </div>
  );
}
