# MCP Apps (Right-Side Tabs) — Design Specification

- **Date:** 2026-11-17
- **Status:** Draft (brainstormed, pending implementation plan)
- **Sub-project:** Frontend #6 — render MCP Apps from MCP servers in a right-side tab panel, with a backend MCP relay and a SEP-1865 sandbox page.

## 1. Context and Scope

The initial spec says MCP Apps are shown as tabs "on the left"; **this is corrected to the right** (Claude.ai style): when an MCP app starts, a tab opens on the right taking half the width; when no app has started, the chat occupies the full width; each tab is closable.

Pydantic AI already detects MCP Apps and, via its AG-UI adapter, emits an `ACTIVITY_SNAPSHOT` (`activity_type: "mcp-apps"`) carrying `{resourceUri, toolInput, result, serverId}` after an app-tool result. This sub-project builds the relay, sandbox, and UI around that.

### 1.1 What this sub-project encompasses

- Backend: an explicit MCP toolset `id` (for `serverId` routing), session-scoped MCP relay endpoints (`resources/read`, `tools/call`), and a `/sandbox` page.
- Frontend: a relative `/api` base + Vite proxy; subscribing to `ACTIVITY_SNAPSHOT`; a right-side closable tab panel rendering apps via `@mcp-ui/client`.
- E2E: real test MCP server + scripted model → tab opens and app renders.

### 1.2 Boundaries / notes

- **All MCP app content is proxied by the backend** (HTTP- or stdio-hosted): the browser never contacts the MCP server directly. (Matches the `jrialland` example.)
- The `MCPToolset` does not advertise the `io.modelcontextprotocol/ui` extension by default; servers that gate app tools on advertising may not expose them (documented limitation).
- Deferred: none new (this completes MCP Apps in the roadmap).

### 1.3 Dependencies

- `agentbox-api`, `agentbox-providers`, `apps/web`; `@mcp-ui/client`, `@modelcontextprotocol/ext-apps` (mcp-ui's 1.x line).

## 2. Decisions and Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Lean on Pydantic AI's **built-in `ACTIVITY_SNAPSHOT`** (no custom event). | The AG-UI adapter already emits it on app-tool results. |
| D2 | Set an explicit `MCPToolset(id=...)` per MCP server. | `serverId`/`serverHash` in the snapshot are the toolset id; needed to route relay requests. |
| D3 | **Backend proxies all app content** (`resources/read`, `tools/call`). | MCP servers (esp. stdio) are only reachable from the backend; keeps the browser sandboxed from servers. |
| D4 | Right-side **tab panel** (corrected from "left"). | Claude.ai-style; chat halves when a tab is open, full width otherwise; tabs closable. |
| D5 | `@mcp-ui/client` `<AppRenderer>` in **no-client mode** with callback proxies. | Least code; its no-client mode is exactly "backend proxies MCP". |
| D6 | SPA↔API on the **same domain** via `/api` + Vite proxy; sandbox page on a **separate origin** via `VITE_SANDBOX_URL`. | Same-domain SPA/API as requested; the SEP-1865 sandbox still needs its own origin (dev: backend `:8000` vs SPA `:5173`; prod: `sandbox.<domain>`). |

## 3. Backend

### 3.1 Toolset id
- `McpToolBinding` gains an `id: str = ""` (default: a slug of `server_url`).
- `build_agent` calls `MCPToolset(server_url, id=binding.id or slug(server_url))`.
- Result: the built-in `ACTIVITY_SNAPSHOT` carries a stable `serverId`.

### 3.2 MCP relay (session-scoped)
- `POST /sessions/{sid}/mcp/{serverId}/resources/read {uri}` → build the session agent's `MCPToolset` for `serverId`, connect, `read_resource_for_app(uri)`, disconnect → return the `ReadResourceResult` (preserving the item MIME type + `_meta.ui` CSP/permissions).
- `POST /sessions/{sid}/mcp/{serverId}/tools/call {name, arguments}` → `call_tool_for_app(name, arguments)` → `CallToolResult`.
- The relay resolves `serverId` → the agent's MCP binding (via `AgentSpec.tool_bindings`), so it works for HTTP and stdio servers (stdio: the backend launches the server).

### 3.3 Sandbox page
- `GET /sandbox` (served by the backend) → the SEP-1865 sandbox bootstrap: an outer-origin relay page that creates the inner iframe, applies `sandbox`/`allow`/CSP (from `_meta.ui`), and relays `postMessage`. CSP is sent as an HTTP header.
- In dev, this is a different origin than the SPA (`:8000` vs `:5173`); in prod, serve at `sandbox.<domain>` and point `VITE_SANDBOX_URL` there.

### 3.4 Schema
- Regenerate `apps/web/openapi.json` + `schema.d.ts`.

## 4. Frontend

### 4.1 API base
- `VITE_API_URL = "/api"` (relative) and a Vite dev proxy forwarding `/api` → `http://localhost:8000`.
- `VITE_SANDBOX_URL` (absolute; default `http://localhost:8000/sandbox` in dev).

### 4.2 App signal → tabs
- The AG-UI client surfaces `ACTIVITY_SNAPSHOT` events (activityType `"mcp-apps"`); on receipt, open a tab keyed by `toolCallId` holding `{serverId, resourceUri, toolInput, result}`.

### 4.3 Right-side panel
- Layout: when ≥1 open tab, the chat takes the left half and a right panel takes the other half with Mantine `<Tabs>`; when no tabs, the chat is full width. Each tab is closable; closing all restores full width.

### 4.4 App rendering
- Each tab renders `<AppRenderer>` (`@mcp-ui/client`) in no-client mode:
  - `toolName`, `toolInput`, `toolResult`, `html` (fetched from the relay's `resources/read`),
  - `sandbox={{ url: new URL(VITE_SANDBOX_URL), csp }}`,
  - `hostCapabilities={{ openLinks: {}, serverTools: {}, serverResources: {}, logging: {} }}`,
  - `onCallTool` / `onReadResource` → the relay endpoints, `onOpenLink` (window.open), `onMessage` (append to chat), `onSizeChanged`.

## 5. Testing (E2E-first)

- **Backend pytest**: a real test MCP server (FastMCP over HTTP) exposing an app tool (`_meta.ui.resourceUri`) + a `ui://` resource; assert the relay's `resources/read`/`tools/call`; assert the chat stream emits `ACTIVITY_SNAPSHOT` (activityType `mcp-apps`) when the app tool is called (scripted model).
- **Frontend E2E** (real stack): the test MCP server + a scripted test model that calls the app tool → send → the right panel opens a tab and the app HTML renders in the sandboxed iframe.

## 6. Error Handling

- Relay/tool errors → returned to the app (MCP error result) and logged; tab shows an error state if the resource fails to load.
- Tab open with a missing resource → an error card in the tab.

## 7. Open Items / Future Work

- Advertise the `io.modelcontextprotocol/ui` extension from the backend MCP client (for servers that gate app tools on advertising) — future.
- Strict SEP-1865 separate-origin in prod (sandbox subdomain) — deployment config.

## References

- Initial spec — `docs/initial_spec.md`; roadmap — `docs/ROADMAP.md` (right-side correction applied).
- MCP Apps reference: `https://github.com/jrialland/minimal-agent-example`.
- SEP-1865 / ext-apps: `https://github.com/modelcontextprotocol/ext-apps`.
- `@mcp-ui/client`: `https://mcpui.dev/`.
