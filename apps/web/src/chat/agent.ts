export interface SendOptions {
  mode: string;
  fork?: boolean;
  forkFromTurnId?: string | null;
  attachmentIds?: string[];
  skill?: string | null;
  retryTurnId?: string | null;
}

export type AgUiStreamEvent = {
  type: string;
  [key: string]: unknown;
};

export async function* streamChat(opts: {
  baseUrl: string;
  token: string | null;
  sessionId: string;
  send: SendOptions;
  content: string;
}): AsyncGenerator<AgUiStreamEvent> {
  const response = await fetch(
    `${opts.baseUrl}/sessions/${opts.sessionId}/messages`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...(opts.token ? { Authorization: `Bearer ${opts.token}` } : {}),
      },
      body: JSON.stringify({
        content: opts.content,
        mode: opts.send.mode,
        fork: opts.send.fork ?? false,
        fork_from_turn_id: opts.send.forkFromTurnId ?? null,
        attachment_ids: opts.send.attachmentIds ?? [],
        skill: opts.send.skill ?? null,
        retry_turn_id: opts.send.retryTurnId ?? null,
      }),
    },
  );
  if (!response.ok) {
    throw new Error(`Chat request failed (${response.status})`);
  }
  const reader = response.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const data = block
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        if (data) yield JSON.parse(data) as AgUiStreamEvent;
        boundary = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}


