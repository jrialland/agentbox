# MCP Apps (Right-Side Tabs) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Checkboxes track progress.

**Goal:** Render MCP Apps from MCP servers in a right-side closable tab panel, with a backend MCP relay and a SEP-1865 sandbox page; real-stack E2E.

**Architecture:** Pydantic AI's AG-UI adapter emits `ACTIVITY_SNAPSHOT` (`activity_type: "mcp-apps"`) on app-tool results (requires an explicit `MCPToolset(id=...)`). The browser opens a right-side tab on that event and renders the app with `@mcp-ui/client` `<AppRenderer>` in no-client mode; `onReadResource`/`onCallTool` go to session-scoped backend relay endpoints that connect to the MCP server (HTTP or stdio) and proxy. The SPA↔API uses a relative `/api` base + Vite proxy; the sandbox page is served by the backend on its own origin (`VITE_SANDBOX_URL`).

**Tech Stack:** pydantic-ai `MCPToolset`, `mcp` 2.x (`MCPServer`), FastAPI, React 19, Mantine v9, `@mcp-ui/client` 7.1.1 (`ext-apps` 1.x), Bun, Vitest, Playwright.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `packages/agentbox-harness/src/agentbox_harness/spec.py` | `McpToolBinding.id` |
| `packages/agentbox-harness/src/agentbox_harness/agent_factory.py` | wire `MCPToolset(id=...)` |
| `packages/agentbox-api/src/agentbox_api/mcp_relay.py` | session-scoped relay (`resources/read`, `tools/call`) |
| `packages/agentbox-api/src/agentbox_api/routers/sessions.py` | relay endpoints (reuse `_build_harness`) |
| `packages/agentbox-api/src/agentbox_api/schemas.py` | `ReadResourceBody`, `CallToolBody` |
| `packages/agentbox-api/src/agentbox_api/sandbox.py` | sandbox page HTML + CSP |
| `packages/agentbox-api/src/agentbox_api/app.py` | `GET /sandbox` |
| `packages/agentbox-api/tests/mcp_app_server.py` | real test MCP server (`MCPServer`) |
| `packages/agentbox-api/tests/test_mcp_relay.py` | relay + snapshot tests |
| `apps/web/vite.config.ts` | `/api` proxy |
| `apps/web/src/api/client.ts` | relative `/api` base |
| `apps/web/src/chat/useChat.ts` | `ACTIVITY_SNAPSHOT` → open tab |
| `apps/web/src/chat/apps.ts` | app-tab store + types |
| `apps/web/src/chat/AppPanel.tsx` | right-side tabs + `AppRenderer` |
| `apps/web/src/pages/SessionPage.tsx` | chat + panel layout |
| `apps/web/e2e/mcp_app_server.py`, `mcp-apps.spec.ts` | E2E |

---

### Task 1: Backend — toolset id

**Files:** `spec.py`, `agent_factory.py`, `tests/test_agent_factory.py` (add).

- [ ] **Step 1: Add `id` to `McpToolBinding`**

```python
class McpToolBinding(BaseModel):
    id: str = ""
    server_url: str
    tool_prefix: str = ""
```

- [ ] **Step 2: Wire `MCPToolset(id=...)` in `agent_factory.py`**

Add a `_slug` helper and set the id:
```python
def _slug(url: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-") or "mcp"
```
```python
for binding in spec.tool_bindings:
    if isinstance(binding, McpToolBinding):
        mcp_sets.append(MCPToolset(
            binding.server_url,
            id=binding.id or _slug(binding.server_url),
            tool_prefix=binding.tool_prefix,
        ))
```

- [ ] **Step 3: Test the slug helper**

```python
def test_slug():
    from agentbox_harness.agent_factory import _slug
    assert _slug("http://localhost:9000/mcp") == "http-localhost-9000-mcp"
```

- [ ] **Step 4: Run + commit**

```powershell
uv run pytest packages/agentbox-harness/tests -q
git add -A && git commit -m "feat(harness): explicit MCP toolset id for MCP Apps routing"
```

---

### Task 2: Backend — MCP relay

**Files:** `mcp_relay.py` (create), `schemas.py`, `routers/sessions.py`, `tests/mcp_app_server.py` (create), `tests/test_mcp_relay.py` (create).

- [ ] **Step 1: Create `mcp_relay.py`**

```python
"""Session-scoped MCP relay for MCP Apps (all app content proxied by the backend)."""
from __future__ import annotations

import logging

from mcp.types import CallToolResult, ReadResourceResult
from pydantic_ai.mcp import MCPToolset

from agentbox_harness.agent_factory import _slug
from agentbox_harness.harness import Harness
from agentbox_harness.spec import McpToolBinding

_log = logging.getLogger(__name__)


def mcp_binding_for(harness: Harness, server_id: str) -> McpToolBinding:
    for binding in harness.spec.tool_bindings:
        if isinstance(binding, McpToolBinding):
            sid = binding.id or _slug(binding.server_url)
            if sid == server_id:
                return binding
    raise KeyError(server_id)


def _toolset(binding: McpToolBinding) -> MCPToolset:
    return MCPToolset(
        binding.server_url,
        id=binding.id or _slug(binding.server_url),
        tool_prefix=binding.tool_prefix,
    )


async def read_resource_for_session(
    harness: Harness, server_id: str, uri: str
) -> ReadResourceResult:
    toolset = _toolset(mcp_binding_for(harness, server_id))
    async with toolset:
        return await toolset.read_resource_for_app(uri)


async def call_tool_for_session(
    harness: Harness, server_id: str, name: str, arguments: dict
) -> CallToolResult:
    toolset = _toolset(mcp_binding_for(harness, server_id))
    async with toolset:
        return await toolset.call_tool_for_app(name, arguments)
```

- [ ] **Step 2: Add schemas**

```python
class ReadResourceBody(BaseModel):
    uri: str

class CallToolBody(BaseModel):
    name: str
    arguments: dict = {}
```

- [ ] **Step 3: Relay endpoints in `sessions.py`**

```python
from mcp.types import CallToolResult, ReadResourceResult
from agentbox_api.mcp_relay import call_tool_for_session, read_resource_for_session

@router.post(
    "/{sid}/mcp/{server_id}/resources/read",
    response_model=ReadResourceResult,
    summary="Read an MCP app resource",
)
async def read_app_resource(sid, server_id, body, request, db, user):
    row = await get_session_or_404(db, sid)
    await require_session_view(db, row, user)
    from agentbox_models.tables.core import Agent
    agent = await db.get(Agent, row.agent_id)
    harness = await _build_harness(agent, request.app.state, user)
    return await read_resource_for_session(harness, server_id, body.uri)

@router.post(
    "/{sid}/mcp/{server_id}/tools/call",
    response_model=CallToolResult,
    summary="Call an MCP app tool",
)
async def call_app_tool(sid, server_id, body, request, db, user):
    row = await get_session_or_404(db, sid)
    await require_session_view(db, row, user)
    from agentbox_models.tables.core import Agent
    agent = await db.get(Agent, row.agent_id)
    harness = await _build_harness(agent, request.app.state, user)
    return await call_tool_for_session(harness, server_id, body.name, body.arguments)
```

(`_build_harness` and `get_session_or_404` are the helpers from the chat sub-project.)

- [ ] **Step 4: Test MCP server (`tests/mcp_app_server.py`)**

```python
"""A real test MCP server exposing an MCP App tool + a ui:// resource."""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

APP_URI = "ui://test/app.html"

mcp = MCPServer("agentbox-test-app")


@mcp.tool(meta={"ui": {"resourceUri": APP_URI}})
def show_app(text: str = "hello") -> str:
    """Render the demo MCP app."""
    return f"App result: {text}"


@mcp.resource(APP_URI)
def app_html() -> str:
    return "<html><body><h1>Hello MCP App</h1></body></html>"


def main() -> None:
    import sys
    mcp.run(transport="streamable-http", host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 9000)


if __name__ == "__main__":
    main()
```

> **Verify** the `MCPServer.run` transport kwarg / HTTP path (`/mcp`) when implementing; adjust `server_url` accordingly.

- [ ] **Step 5: Relay test (against the real server, random port)**

```python
from agentbox_api.mcp_relay import call_tool_for_session, read_resource_for_session
from tests.mcp_app_server import APP_URI, mcp

async def test_read_resource_for_app():
    from pydantic_ai.mcp import MCPToolset
    toolset = MCPToolset(mcp)  # in-process FastMCP/MCPServer
    async with toolset:
        result = await toolset.read_resource_for_app(APP_URI)
    assert "<h1>" in result.contents[0].text

async def test_call_tool_for_app():
    from pydantic_ai.mcp import MCPToolset
    toolset = MCPToolset(mcp)
    async with toolset:
        result = await toolset.call_tool_for_app("show_app", {"text": "x"})
    assert "App result: x" in result.content[0].text
```

> If `MCPToolset(mcp)` (in-process) isn't supported, start `MCPServer` over HTTP on a random port in an async fixture and use its URL.

- [ ] **Step 6: Run + commit**

```powershell
uv run pytest packages/agentbox-api/tests/test_mcp_relay.py -q
git add -A && git commit -m "feat(api): session-scoped MCP relay for MCP Apps"
```

---

### Task 3: Backend — sandbox page + ACTIVITY_SNAPSHOT test

**Files:** `sandbox.py` (create), `app.py`, `tests/test_sandbox.py` (add).

- [ ] **Step 1: Sandbox page**

```python
"""SEP-1865 MCP App sandbox page (relay between host and the app iframe)."""
from fastapi.responses import HTMLResponse

SANDBOX_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>MCP App Sandbox</title></head><body>
<script>
  const iframe = document.createElement('iframe');
  iframe.setAttribute('sandbox', 'allow-scripts allow-forms allow-popups');
  iframe.style.cssText = 'width:100%;height:100%;border:0';
  window.addEventListener('message', (e) => {
    if (e.source === window.parent) {
      if (e.data && e.data.method === 'ui/initialize') return;
      if (e.data && e.data.method === 'ui/render') {
        iframe.srcdoc = e.data.params.html;
        return;
      }
    }
    if (e.source === iframe.contentWindow) window.parent.postMessage(e.data, '*');
  });
  document.body.appendChild(iframe);
</script></body></html>"""

def sandbox_response() -> HTMLResponse:
    return HTMLResponse(
        SANDBOX_HTML,
        headers={"Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; frame-src 'self' data: blob: https:; connect-src 'none'"},
    )
```

> **Contract note:** confirm the exact message protocol the `@mcp-ui/client` `<AppRenderer>`'s outer iframe expects (inspect its source during Task 6); adjust the relay accordingly.

- [ ] **Step 2: Mount `GET /sandbox` in `app.py`**

```python
from agentbox_api.sandbox import sandbox_response

@app.get("/sandbox", include_in_schema=False)
async def sandbox_page():
    return sandbox_response()
```

- [ ] **Step 3: Test**

```python
def test_sandbox_page(client):
    r = client.get("/sandbox")
    assert r.status_code == 200
    assert "Content-Security-Policy" in r.headers
```

- [ ] **Step 4: Test ACTIVITY_SNAPSHOT emission** (scripted model + real MCP server)

```python
async def test_app_tool_emits_activity_snapshot(...):
    # agent with mcp binding to the in-process/http test MCP server + "test" provider
    # stream /sessions/{sid}/messages, collect SSE events, assert one has type "ACTIVITY_SNAPSHOT"
    assert any('"type":"ACTIVITY_SNAPSHOT"' in e for e in events)
    assert any('"mcp-apps"' in e for e in events)
```

> **Verify** `TestModel` calls the MCP tool; if not, add a deterministic `test-mcp` provider (a `FunctionModel` that calls `info.function_tools[0]` with valid args).

- [ ] **Step 5: Run + commit**

```powershell
uv run pytest packages/agentbox-api/tests -q
git add -A && git commit -m "feat(api): MCP Apps sandbox page + ACTIVITY_SNAPSHOT test"
```

---

### Task 4: Frontend — relative `/api` + Vite proxy

**Files:** `vite.config.ts`, `src/api/client.ts`, `.env`/e2e env, `playwright.config.ts`.

- [ ] **Step 1: Vite proxy**

```ts
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true } },
  },
});
```

- [ ] **Step 2: Relative API base**

```ts
const API_URL = import.meta.env.VITE_API_URL ?? "/api";
```

(Keep `openapi` fetch base = `API_URL`.)

- [ ] **Step 3: Env for dev/prod/E2E**

- `.env.example`: `VITE_API_URL=/api`, `VITE_SANDBOX_URL=http://localhost:8000/sandbox`.
- E2E `prepare.ts`: set `VITE_API_URL=/api` (Vite proxies to the e2e backend) and remove absolute `VITE_API_URL=http://localhost:8000`; tests' direct `request` calls still use `http://localhost:8000`.

- [ ] **Step 4: Run Vitest + build + commit**

```powershell
Set-Location apps/web; bun run test; bun run build
git add -A && git commit -m "chore(web): relative /api + Vite proxy; sandbox url env"
```

---

### Task 5: Frontend — right-side tabs

**Files:** `src/chat/apps.ts` (create), `src/chat/useChat.ts`, `src/pages/SessionPage.tsx`, `src/chat/AppPanel.tsx` (create), `src/styles/*` (layout).

- [ ] **Step 1: App-tab store/types**

```ts
export type AppTab = {
  toolCallId: string;
  serverId: string;
  resourceUri: string;
  toolInput: unknown;
  toolResult: unknown;
};
```

- [ ] **Step 2: `ACTIVITY_SNAPSHOT` handler in `useChat`**

```ts
onActivitySnapshot: (p) => {
  if (p.activityType !== "mcp-apps") return;
  const { resourceUri, toolInput, result, serverId } = p.content as any;
  setAppTabs((tabs) =>
    tabs.some((t) => t.toolCallId === p.messageId)
      ? tabs
      : [...tabs, { toolCallId: p.messageId, serverId, resourceUri, toolInput, toolResult: result }]
  );
},
```

> **Verify** the actual `@ag-ui/client` callback name/types for `ACTIVITY_SNAPSHOT` (`onActivitySnapshot` vs event in `onEvent`); adjust.

- [ ] **Step 3: Layout + `AppPanel`**

In `SessionPage`, when `appTabs.length > 0` render a two-column flex: chat (left half) + `<AppPanel tabs onClose>` (right half); else chat full width. `AppPanel` uses Mantine `<Tabs>` with closable tabs (one per `AppTab`, keyed by `toolCallId`); closing removes from the store.

- [ ] **Step 4: Vitest for the tab open/close/layout**

```tsx
it("opens a right-side tab on an activity snapshot and restores full width on close", async () => {
  // mock useChat to emit an ACTIVITY_SNAPSHOT event, render SessionPage,
  // assert the right panel + tab appear, click close, assert full-width chat
});
```

- [ ] **Step 5: Run + commit**

```powershell
Set-Location apps/web; bun run test; bun run build
git add -A && git commit -m "feat(web): right-side MCP App tab panel"
```

---

### Task 6: Frontend — AppRenderer

**Files:** `src/chat/AppPanel.tsx` (extend), `src/chat/apps.ts` (relay helpers), `package.json` (`@mcp-ui/client`).

- [ ] **Step 1: Add `@mcp-ui/client`**

```powershell
Set-Location apps/web; bun add @mcp-ui/client
```

- [ ] **Step 2: Render each tab** (inspect `node_modules/@mcp-ui/client` AppRenderer source first)

```tsx
import { AppRenderer } from "@mcp-ui/client";
import { getReadResourceFn, getCallToolFn } from "./apps";

<AppRenderer
  toolName={tab.toolCallId}
  toolInput={tab.toolInput ?? undefined}
  toolResult={tab.toolResult}
  html={html}                      // from resources/read (ui://…)
  sandbox={{ url: new URL(import.meta.env.VITE_SANDBOX_URL), csp }}
  hostCapabilities={{ openLinks: {}, serverTools: {}, serverResources: {}, logging: {} }}
  onReadResource={getReadResourceFn(sessionId, tab.serverId)}
  onCallTool={getCallToolFn(sessionId, tab.serverId)}
  onOpenLink={(url) => window.open(url, "_blank", "noopener,noreferrer")}
/>
```

- [ ] **Step 3: Fetch app HTML** via `POST /sessions/{sid}/mcp/{serverId}/resources/read {uri: tab.resourceUri}` (TanStack Query); extract the `text` content + `_meta.ui.csp`.

- [ ] **Step 4: Run + commit**

```powershell
Set-Location apps/web; bun run build; bun run test
git add -A && git commit -m "feat(web): render MCP Apps in the right panel"
```

---

### Task 7: E2E — app tab opens and renders

**Files:** `e2e/mcp_app_server.py` (create), `playwright.config.ts`, `e2e/mcp-apps.spec.ts` (create), `e2e/prepare.ts`.

- [ ] **Step 1: E2E test MCP server** — copy `tests/mcp_app_server.py` into `e2e/` (or run the package one) and add a Playwright `webServer` entry `:9000`.

- [ ] **Step 2: Seed an agent with the MCP binding + "test" provider** (`prepare.ts`): `{model:"test", mcp_tools:[{server_url:"http://localhost:9000/mcp", id:"test-app"}]}`.

- [ ] **Step 3: Spec**

```ts
test("opens a right-side MCP App tab", async ({ page }) => {
  await page.goto("/");
  await login(page);
  await createProject(page, "MCP");
  await addAgent(page, { name: "AppAgent", model: "test", mcp: "test-app" });
  await createSession(page, "MCP", "AppAgent");
  await page.getByRole("textbox").fill("show the app");
  await page.getByRole("button", { name: "Send" }).click();
  const panel = page.getByTestId("app-panel");
  await expect(panel).toBeVisible({ timeout: 30_000 });
  await expect(panel.getByRole("tab").first()).toBeVisible();
  await expect(panel.locator("iframe")).toBeVisible();
});
```

- [ ] **Step 4: Run E2E + commit**

```powershell
Set-Location apps/web; bun run e2e
git add -A && git commit -m "test(web): E2E MCP App tab opens/renders"
```

---

## Notes

- **Sandbox contract**: inspect `@mcp-ui/client`'s `<AppRenderer>` source + the `ext-apps` sandbox before finalizing `sandbox.py` (Task 3/6) — the outer-iframe message protocol must match.
- **Dev origin**: backend `:8000` vs SPA `:5173` are different origins (sandbox compliant in dev); prod must serve the sandbox at `sandbox.<domain>` via `VITE_SANDBOX_URL`.
- Verify `TestModel` calls the MCP app tool for the ACTIVITY_SNAPSHOT/E2E; if not, add a deterministic `test-mcp` provider.
