# Agentbox — Specification Coverage Roadmap

Maps every requirement from `docs/initial_spec.md` to its current status so nothing is lost. Status legend:

- **DONE** — implemented and tested.
- **PARTIAL** — partly implemented; gap noted.
- **CURRENT** — being implemented in the active sub-project.
- **DEFERRED** — not yet started; tracked for a future sub-project.
- **DEVIATION** — implemented differently than the literal spec; rationale noted.

## Protocols

| Requirement | Status | Where / Notes |
|---|---|---|
| ACP (Agent Client Protocol) adapter (IDE, JSON-RPC over STDIO) | DONE | `agentbox-acp` / `python -m agentbox_api.acp_server` (official `agent-client-protocol` v1). |
| A2A (Agent-to-Agent) adapter + agent cards + API-key auth | DONE | `a2a-sdk` 1.3; `/a2a/{agent}` (card + JSON-RPC), API-key auth. |
| MCP for external tools/resources | PARTIAL | Agent factory consumes MCP servers via pydantic-ai `MCPToolset`; no MCP server management UI yet. |
| AG-UI streaming (agent → web UI) | DONE | Backend uses pydantic-ai `AGUIAdapter`; frontend consumes it via `@ag-ui/client`. |
| Full compliance with the protocols (no homegrown protocol code) | DONE (AG-UI, ACP, A2A) | AG-UI + ACP use pydantic-ai/the official SDK; MCP via pydantic-ai. |
| Extensive research on libraries/protocols | DONE | Captured in the per-sub-project specs. |

## User privileges (RBAC)

| Requirement | Status | Where / Notes |
|---|---|---|
| Roles → permissions; users → roles | DONE | `agentbox-models` tables + `agentbox-api` auth backend. |
| Admin CRUD users / roles | DONE | `users` + `roles` routers. |
| Admin CRUD permissions | DONE | `/permissions` CRUD; role↔permission and user↔role assignment; role/user update; Admin UI (Permissions/Roles/Users tabs). |
| Personal API keys (scoped, optional lifetime) | DONE | Optional `expires_at` (enforced at auth), scope-subset validation, soft revoke, personal no-hash reads, API-keys page. |
| API keys authenticate the API | DONE | `JWTAuthenticationBackend` accepts API keys. |

## Use case 1 — Agent creation

| Requirement | Status | Where / Notes |
|---|---|---|
| Agent = system prompt + tools | DONE | Harness + agents router + management UI. |
| File tools (Codex / MCP FileSystem parity) | DONE | `FilesystemToolbox` mirrors MCP FileSystem tool set, sandboxed to project root. |
| Agent definition (name, description, prompt, tools, sub-agents, model) | DONE | `AgentSpec` + full agent create form. |
| Sub-agents | DONE | Harness agents-as-tools (isolated runs). |
| Agent avatar (attach photo) | DONE | `GET/PUT/DELETE /agents/{name}/avatar`; normalized 300×300 PNG upload; create-form picker + per-row change/remove. |
| **RoboHash avatars (set #1) by default + copyright notices** | DONE | Local `robohash` lib (`roboset="set1"`), seeded by agent id; `NOTICE` + README credits (Zikri Kader, CC-BY). |

## Use case 2 — LLM configuration

| Requirement | Status | Where / Notes |
|---|---|---|
| Provider types: OpenAI legacy, OpenAI Responses, Anthropic, generic | DONE | `agentbox-providers.resolve_model`. |
| Generic provider (base URL + API key + API type) | DONE | — |
| Known providers: Moonshot, DeepSeek (pre-filled URL, env-var key) | DONE | Resolver + env-var API keys. |
| Model list from provider endpoints | DONE | `list_models` + refresh/persist. |

## Use case 3 — Session on a project (chat)

| Requirement | Status | Where / Notes |
|---|---|---|
| Project = folder on PC | DONE | Projects + tree. |
| Left tree: projects → sessions | DONE | `ProjectTree`. |
| Choose agent + chat interface | DONE | Chat sub-project. |
| AG-UI-compatible chat window | DONE | AG-UI client (`@ag-ui/client`). |
| Input form with attachments (paperclip) | DONE | Multimodal attachments. |
| Speech-to-text (Web Audio API, microphone) | DONE | Web Speech API. |
| Autocomplete `/` for installed **skills** | DONE | Composer `/` menu; `skill=<name>` explicit activation. |
| Autocomplete `@` for filenames (project root) | DONE | `GET /sessions/{sid}/files` + composer `@` menu (inserts `@relative/path`). |
| Streamed tokens; visible reasoning; Markdown; Mermaid + pan/zoom + copy-source | DONE | Chat sub-project. |
| Direct mode: closing browser ends the session | DEVIATION | Harness supports detach/re-attach (run continues); documented in the harness spec. |
| Resume existing session | DONE | Loads history. |
| Edit a previous question → conversation restarts | DONE | Fork via `fork_from_turn_id`. |
| Mode switching (Ask / Agent) | DONE | Mode selector. |
| Agent modes defined in the agent config UI | DONE | Modes editor in the agent form. |

## Use case 4 — ACP

| Requirement | Status | Notes |
|---|---|---|
| External IDE drives sessions via ACP (RPC over STDIO) | DONE | ACP v1 agent over stdio; full session lifecycle; image/audio/embedded + stdio MCP. |

## Use case 5 — A2A

| Requirement | Status | Notes |
|---|---|---|
| Start an agentic session via A2A using an API key | DONE | API-key-authenticated `/a2a/{agent}`. |
| Only designated agents (with an agent card) support A2A | DONE | `GET/PUT/DELETE /agents/{name}/card` + card UI. |

## MCP Apps

| Requirement | Status | Notes |
|---|---|---|
| Render MCP Apps from MCP servers | DONE | Backend MCP relay + `@mcp-ui/client` `AppRenderer` in no-client mode; app content proxied by the backend. |
| Shown as tabs **on the right of the conversation** (corrected from the original "left"; Claude.ai style) | DONE | `AppPanel` halves the chat when a tab is open; tabs closable. |

## Technical stack

| Requirement | Status | Notes |
|---|---|---|
| Python + Pydantic AI harness | DONE | `agentbox-harness`. |
| Agents/models/settings in SQLite | DONE | `agentbox-models`. |
| Async wherever possible | DONE | Async throughout. |
| Backend: FastAPI, SQLModel, **loguru** | DONE | FastAPI + SQLModel; `loguru.logger` used across the API (config/sinks deferred). |
| Monorepo via **Uv Workspaces** | DONE (Python) / DEVIATION (frontend) | Python packages are a Uv workspace; the React app is a separate Bun project in `apps/web`. |
| UI: React + **Mantine** + **Bulma** + **RemixIcons**, light/dark (system) | DONE | `apps/web`; Mantine widgets, Bulma layout, RemixIcons, `ThemeSync`. |
| Precise components, message bus, no oversimplification | DONE | Component split + typed `mitt` bus. |
| Protocol compliance mandatory (no homegrown) | DONE (AG-UI, ACP, A2A) | — |

## Sub-project history

| # | Sub-project | Spec | Plan |
|---|---|---|---|
| 1 | Agentic harness | `specs/2026-11-17-agentic-harness-design.md` | `plans/2026-11-17-agentic-harness.md` |
| 2 | Foundation (monorepo + data model + persistence) | `specs/2026-11-17-foundation-design.md` | `plans/2026-11-17-foundation.md` |
| 3 | LLM provider layer | `specs/2026-11-17-provider-layer-design.md` | `plans/2026-11-17-provider-layer.md` |
| 4 | Backend (FastAPI + RBAC/JWT + AG-UI) | `specs/2026-11-17-backend-design.md` | `plans/2026-11-17-backend.md` |
| 5 | Web scaffold + design system | `specs/2026-11-17-web-scaffold-design.md` | `plans/2026-11-17-web-scaffold.md` |
| 6 | Frontend auth | `specs/2026-11-17-web-auth-design.md` | `plans/2026-11-17-web-auth.md` |
| 7 | Projects + session tree | `specs/2026-11-17-web-projects-tree-design.md` | `plans/2026-11-17-web-projects-tree.md` |
| 8 | Agents + providers management (E2E) | `specs/2026-11-17-web-management-design.md` | `plans/2026-11-17-web-management.md` |
| 9 | Chat (core + edit/fork + composer) | `specs/2026-11-17-web-chat-design.md` | `plans/2026-11-17-web-chat.md` |
| 10 | MCP Apps (right-side tabs + relay + sandbox) | `specs/2026-11-17-web-mcp-apps-design.md` | `plans/2026-11-17-web-mcp-apps.md` |
| 11 | Agent avatars (RoboHash set1 + custom photo) | `specs/2026-11-17-agent-avatars-design.md` | `plans/2026-11-17-agent-avatars.md` |
| 12 | Backend loguru logging (usage) | `specs/2026-11-17-logging-design.md` | `plans/2026-11-17-logging.md` |
| 13 | RBAC administration (permissions CRUD + assignments + admin UI) | `specs/2026-11-17-rbac-admin-design.md` | `plans/2026-11-17-rbac-admin.md` |
| 14 | API keys (lifetime + scope validation + page) | `specs/2026-11-17-api-keys-design.md` | `plans/2026-11-17-api-keys.md` |
| 15 | ACP adapter (IDE over stdio) | `specs/2026-11-17-acp-design.md` | `plans/2026-11-17-acp.md` |
| 16 | Provider edit + model management + session delete | `specs/2026-11-17-provider-model-admin-design.md` | `plans/2026-11-17-provider-model-admin.md` |
| 17 | A2A adapter (agent cards, API-key auth) | `specs/2026-11-17-a2a-design.md` | `plans/2026-11-17-a2a.md` |
| 18 | Agent Skills (discovery, activation, UI) | `specs/2026-11-17-skills-design.md` | `plans/2026-11-17-skills.md` |
| 19 | @ file autocomplete | `specs/2026-11-17-file-mentions-design.md` | `plans/2026-11-17-file-mentions.md` |

## Deferred backlog (not yet scheduled)

1. **loguru configuration** (console/file sinks, rotation, uvicorn/stdlib interception) — usage is done, config deferred.
