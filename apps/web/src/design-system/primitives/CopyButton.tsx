import { RiCheckLine, RiFileCopyLine } from "@remixicon/react";
import { useState } from "react";

import { Icon } from "../icons/Icon";

export function CopyButton({
  value,
  label = "Copy",
}: {
  value: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <button type="button" onClick={copy} aria-label={copied ? "Copied" : label}>
      <Icon as={copied ? RiCheckLine : RiFileCopyLine} size={16} />
      {copied ? "Copied" : label}
    </button>
  );
}
