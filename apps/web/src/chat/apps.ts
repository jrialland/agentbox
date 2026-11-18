export type AppTab = {
  id: string;
  serverId: string;
  resourceUri: string;
  toolInput: unknown;
  toolResult: unknown;
};

export function appTabFromSnapshot(event: {
  messageId: string;
  activityType: string;
  content: Record<string, unknown>;
}): AppTab | null {
  if (event.activityType !== "mcp-apps") return null;
  const c = event.content ?? {};
  return {
    id: event.messageId,
    serverId: typeof c.serverId === "string" ? c.serverId : "",
    resourceUri: typeof c.resourceUri === "string" ? c.resourceUri : "",
    toolInput: c.toolInput,
    toolResult: c.result,
  };
}
