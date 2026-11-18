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
| ACP (Agent Client Protocol) adapter (IDE, JSON-RPC over STDIO) | DEFERRED | Future sub-project. |
| A2A (Agent-to-Agent) adapter + agent cards + API-key auth | DEFERRED | Future sub-project (reuses API-key auth). |
| MCP for external tools/resources | PARTIAL | Agent factory consumes MCP servers via pydantic-ai `MCPToolset`; no MCP server management UI yet. |
| AG-UI streaming (agent → web UI) | DONE (backend) / CURRENT (frontend) | Backend uses pydantic-ai `AGUIAdapter`; frontend consumption in the chat sub-project. |
| Full compliance with the protocols (no homegrown protocol code) | DONE (AG-UI) / DEFERRED (ACP, A2A) | AG-UI uses pydantic-ai's adapter; MCP via pydantic-ai. |
| Extensive research on libraries/protocols | DONE | Captured in the per-sub-project specs. |

## User privileges (RBAC)

| Requirement | Status | Where / Notes |
|---|---|---|
| Roles → permissions; users → roles | DONE | `agentbox-models` tables + `agentbox-api` auth backend. |
| Admin CRUD users / roles | DONE | `users` + `roles` routers. |
| Admin CRUD permissions | DEFERRED | No `/permissions` CRUD router yet (permissions are seeded/attached to roles). |
| Personal API keys (scoped, optional lifetime) | PARTIAL | `api_keys` router (create/list/delete, scopes). Lifetime (`expires_at`) is stored but not exposed by the create endpoint. |
| API keys authenticate the API | DONE | `JWTAuthenticationBackend` accepts API keys. |

## Use case 1 — Agent creation

| Requirement | Status | Where / Notes |
|---|---|---|
| Agent = system prompt + tools | DONE | Harness + agents router + management UI. |
| File tools (Codex / MCP FileSystem parity) | DONE | `FilesystemToolbox` mirrors MCP FileSystem tool set, sandboxed to project root. |
| Agent definition (name, description, prompt, tools, sub-agents, model) | DONE | `AgentSpec` + full agent create form. |
| Sub-agents | DONE | Harness agents-as-tools (isolated runs). |
| Agent avatar (attach photo) | DEFERRED | `Agent.avatar_url` column exists; no UI/logic. |
| **RoboHash avatars (set #1) by default + copyright notices** | DEFERRED | Not implemented; must use RoboHash set 1 when built. |

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
| Choose agent + chat interface | CURRENT | Chat sub-project. |
| AG-UI-compatible chat window | CURRENT | AG-UI client (chat sub-project). |
| Input form with attachments (paperclip) | CURRENT | Multimodal attachments (chat sub-project). |
| Speech-to-text (Web Audio API, microphone) | CURRENT | Web Speech API (chat sub-project). |
| Autocomplete `/` for installed **skills** | DEFERRED | Skills system not built (deferred platform-wide); needs skills + autocomplete. |
| Autocomplete `@` for filenames (project root) | DEFERRED | Needs a file-listing endpoint + autocomplete. |
| Streamed tokens; visible reasoning; Markdown; Mermaid + pan/zoom + copy-source | CURRENT | Chat sub-project. |
| Direct mode: closing browser ends the session | DEVIATION | Harness supports detach/re-attach (run continues); documented in the harness spec. |
| Resume existing session | CURRENT | Chat sub-project (loads history). |
| Edit a previous question → conversation restarts | CURRENT | Chat sub-project (fork via `fork_from_turn_id`). |
| Mode switching (Ask / Agent) | CURRENT | Mode selector in the chat sub-project. |
| Agent modes defined in the agent config UI | DONE | Modes editor in the agent form. |

## Use case 4 — ACP

| Requirement | Status | Notes |
|---|---|---|
| External IDE drives sessions via ACP (RPC over STDIO) | DEFERRED | Future sub-project. |

## Use case 5 — A2A

| Requirement | Status | Notes |
|---|---|---|
| Start an agentic session via A2A using an API key | DEFERRED | Future sub-project. |
| Only designated agents (with an agent card) support A2A | DEFERRED | Needs agent-card management. |

## MCP Apps

| Requirement | Status | Notes |
|---|---|---|
| Render MCP Apps from MCP servers | DEFERRED | Sub-project: backend emits app events; frontend hosts via `@mcp-ui/client`. |
| Shown as tabs **on the right of the conversation** (corrected from the original "left"; Claude.ai style) | DEFERRED | Same sub-project. |

## Technical stack

| Requirement | Status | Notes |
|---|---|---|
| Python + Pydantic AI harness | DONE | `agentbox-harness`. |
| Agents/models/settings in SQLite | DONE | `agentbox-models`. |
| Async wherever possible | DONE | Async throughout. |
| Backend: FastAPI, SQLModel, **loguru** | PARTIAL | FastAPI + SQLModel done; **loguru not wired yet** (uses uvicorn/default logging). |
| Monorepo via **Uv Workspaces** | DONE (Python) / DEVIATION (frontend) | Python packages are a Uv workspace; the React app is a separate Bun project in `apps/web`. |
| UI: React + **Mantine** + **Bulma** + **RemixIcons**, light/dark (system) | DONE | `apps/web`; Mantine widgets, Bulma layout, RemixIcons, `ThemeSync`. |
| Precise components, message bus, no oversimplification | DONE | Component split + typed `mitt` bus. |
| Protocol compliance mandatory (no homegrown) | DONE (AG-UI) / DEFERRED (ACP, A2A) | — |

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
| 9 | Chat (core + edit/fork + composer) | *current* | *next* |

## Deferred backlog (not yet scheduled)

1. **Skills system** + `/` autocomplete.
2. **`@` file autocomplete** (needs a project file-listing endpoint).
3. **RoboHash avatars** (set #1, with required copyright notices) + avatar UI.
4. **MCP Apps** rendered as left-hand tabs.
5. **ACP** adapter (IDE over STDIO).
6. **A2A** adapter + agent cards + A2A enablement per agent.
7. **Permissions CRUD** router (admin UI for permissions).
8. **API-key lifetime** exposure in the create endpoint/UI.
9. **loguru** wiring in the backend.
10. Provider **edit (PUT)** endpoints; **session delete**.
