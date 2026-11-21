import { Button } from "@mantine/core";
import { useState } from "react";

import styles from "./chat.module.css";
import { MarkdownBlock } from "./MarkdownBlock";

export function SummaryNotice({ content }: { content: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={styles.notice} data-testid="summary-notice">
      <div className={styles.noticeHead}>
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

