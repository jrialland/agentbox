import { HttpAgent } from "@ag-ui/client";

export interface SendOptions {
  mode: string;
  fork?: boolean;
  forkFromTurnId?: string | null;
  attachmentIds?: string[];
  skill?: string | null;
}

export function createChatAgent(opts: {
  baseUrl: string;
  token: string | null;
  sessionId: string;
  send: SendOptions;
}) {
  return new HttpAgent({
    url: `${opts.baseUrl}/sessions/${opts.sessionId}/messages`,
    headers: opts.token ? { Authorization: `Bearer ${opts.token}` } : {},
    fetch: ((url: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse((init?.body as string) ?? "{}");
      const messages = (body.messages ?? []) as { role: string; content: unknown }[];
      const lastUser = [...messages].reverse().find((m) => m.role === "user");
      const payload = {
        content: typeof lastUser?.content === "string" ? lastUser.content : "",
        mode: opts.send.mode,
        fork: opts.send.fork ?? false,
        fork_from_turn_id: opts.send.forkFromTurnId ?? null,
        attachment_ids: opts.send.attachmentIds ?? [],
        skill: opts.send.skill ?? null,
      };
      return fetch(url, { ...init, body: JSON.stringify(payload) });
    }) as typeof fetch,
  });
}
