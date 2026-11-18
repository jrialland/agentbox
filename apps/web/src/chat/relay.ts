import { api } from "../api/client";
import type { AppTab } from "./apps";

export async function readAppResource(sessionId: string, tab: AppTab, uri: string) {
  const res = await api.POST("/sessions/{sid}/mcp/{server_id}/resources/read", {
    params: { path: { sid: sessionId, server_id: tab.serverId } },
    body: { uri },
  });
  return res.data;
}

export async function callAppTool(
  sessionId: string,
  tab: AppTab,
  name: string,
  args: Record<string, unknown>,
) {
  const res = await api.POST("/sessions/{sid}/mcp/{server_id}/tools/call", {
    params: { path: { sid: sessionId, server_id: tab.serverId } },
    body: { name, arguments: args },
  });
  return res.data;
}
