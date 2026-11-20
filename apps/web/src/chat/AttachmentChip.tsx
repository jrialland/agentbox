import { RiAttachment2 } from "@remixicon/react";

import { API_URL } from "../config";
import { Badge } from "../design-system/primitives/Badge";
import { Icon } from "../design-system/icons/Icon";
import { useAuthStore } from "../store/auth";
import styles from "./chat.module.css";

export type AttachmentMeta = {
  id: string;
  filename: string;
  media_type?: string;
};

export function AttachmentChip({
  attachment,
  sessionId,
}: {
  attachment: AttachmentMeta;
  sessionId: string;
}) {
  const href = `${API_URL}/sessions/${sessionId}/attachments/${attachment.id}`;

  async function download(event: React.MouseEvent<HTMLAnchorElement>) {
    event.preventDefault();
    const token = useAuthStore.getState().token;
    const response = await fetch(href, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) return;
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = attachment.filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <a
      className={styles.attachment}
      href={href}
      download={attachment.filename}
      onClick={download}
    >
      <Icon as={RiAttachment2} size={16} />
      <span>{attachment.filename}</span>
      {attachment.media_type && (
        <Badge tone="neutral">{attachment.media_type}</Badge>
      )}
    </a>
  );
}
