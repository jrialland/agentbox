# Agentbox — Specification Coverage Roadmap

Maps every requirement from `docs/initial_spec.md` to its current status so nothing is lost. Status legend:

- **DONE** — implemented and tested.
- **PARTIAL** — partly implemented; gap noted.
- **CURRENT** — being implemented in the active sub-project.
- **PLANNED** — scheduled for an upcoming sub-project; spec/plan not written yet.
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
| File tools (Codex / MCP FileSystem parity) | DONE | 17 native tools in `FilesystemToolbox` (read/write/tree/search/info/media/delete), guarded delete, post-tool hooks. |
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
| Left tree: projects → sessions | DONE | `ProjectPanel` uses design-system icon actions and a stable single-row layout. |
| Choose agent + chat interface | DONE | Chat sub-project. |
| AG-UI-compatible chat window | DONE | AG-UI client (`@ag-ui/client`). |
| Input form with attachments (paperclip) | DONE | Paperclip/drop composer; attachment metadata persists on user turns with authenticated history chips and downloads. |
| Speech-to-text (Web Audio API, microphone) | DONE | Web Speech API. |
| Autocomplete `/` for installed **skills** | DONE | Composer `/` menu; `skill=<name>` explicit activation. |
| Autocomplete `@` for filenames (project root) | DONE | `GET /sessions/{sid}/files` + composer `@` menu (inserts `@relative/path`). |
| Streamed tokens; visible reasoning; Markdown; Mermaid + pan/zoom + copy-source | DONE | Ordered live segments preserve event order; summary activity persists; Markdown/highlight.js/copy; Mermaid renders only complete fences with fallback. |
| Direct mode: closing browser ends the session | DEVIATION | Harness supports detach/re-attach (run continues); documented in the harness spec. |
| Resume existing session | DONE | Loads history. |
| Edit a previous question → conversation restarts | DONE | Visible fork banner with Cancel; retry uses `retry_turn_id` without duplicating user turns. |
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
| Only designated agents (with an agent card) support A2A | DONE | Agents with a stored card are exposed. Structured editor with validation, JSON fallback, and in-app help. |

## MCP Apps

| Requirement | Status | Notes |
|---|---|---|
| Render MCP Apps from MCP servers | DONE | Backend MCP relay + `@mcp-ui/client` `AppRenderer` in no-client mode; app content proxied by the backend. |
| Shown as tabs **on the right of the conversation** (corrected from the original "left"; Claude.ai style) | DONE | Resizable desktop split with keyboard-accessible divider; full-screen sheet on mobile; tabs closable. |

## Technical stack

| Requirement | Status | Notes |
|---|---|---|
| Python + Pydantic AI harness | DONE | `agentbox-harness`. |
| Agents/models/settings in SQLite | DONE | `agentbox-models`. |
| Async wherever possible | DONE | Async throughout. |
| Backend: FastAPI, SQLModel, **loguru** | DONE | FastAPI + SQLModel; `loguru.logger` used across the API (sinks configured in #20). |
| Monorepo via **Uv Workspaces** | DONE (Python) / DEVIATION (frontend) | Python packages are a Uv workspace; the React app is a separate Bun project in `apps/web`. |
| UI: React + **Mantine** + **RemixIcons**, light/dark (system) | DONE | Mantine-first design system with RemixIcons, Silkscreen/Inter/JetBrains Mono, dark-first theme + toggle, and Storybook. Bulma has been removed. |
| Precise components, message bus, no oversimplification | DONE | Component split + typed `mitt` bus. |
| Protocol compliance mandatory (no homegrown) | DONE (AG-UI, ACP, A2A) | — |

## UX review remediation (high priority)

Source: [2026-11-20 UX review](reviews/2026-11-20-ux-review/report.md). These workstreams are product-quality remediation and are prioritized ahead of new protocol features. Each gets its own spec → plan → implementation cycle. **UX-1 is the recommended first cycle** because it establishes the visual foundation the other workstreams build on.

| ID | Workstream | Status | Priority | Scope | Source findings |
|---|---|---|---|---|---|
| UX-1 | Design system, shell & product character | DONE | P0/P1 | Brand kit, design tokens, typography, RemixIcon system, responsive shell, nav/sidebar, page titles, empty-state visual language, form layout, dark mode, replace/rescope Bulma. | E1–E6, C1–C2, C7–C10, G |
| UX-2 | Chat surface & runtime UX | DONE | P0/P1 | Markdown stylesheet, safe Mermaid rendering, auto-scroll/sticky composer, thinking/running status, stop control, persisted reasoning/tool traces, attachment history, fork banner, per-turn errors/retry, icon composer. | A1–A12 |
| UX-3 | Contextual help & structured editors | DONE | P1/P2 | A2A structured card editor, provider setup help/test connection, tool/mode/MCP/scope help, tooltips, docs links, guided empty states. | F1–F4, D2, D5, D7, C3–C4 |
| UX-4 | Data integrity, errors & navigation states | DONE | P1/P2 | Required-field/path validation, destructive confirmations, API error propagation, 404/session-not-found, active nav, backend error logging. | B1–B5, C5–C6, H1–H2, D4, A4–A5 |

The visual direction is **technical command center with hacker/computer-culture pop** (pixel display type, phosphor palette, subtle CRT accents). **UX-1 through UX-4, D19, D20, and D21 are complete** - specs `superpowers/specs/2026-11-20-ux-1-design-system-design.md`, `superpowers/specs/2026-11-21-ux-2-chat-surface-design.md`, `superpowers/specs/2026-11-21-ux-3-contextual-help-structured-editors-design.md`, `superpowers/specs/2026-11-21-ux-4-data-integrity-design.md`, `superpowers/specs/2026-11-21-rust-lsp-quiescence-design.md`, `superpowers/specs/2026-11-21-agents-md-project-instructions-design.md`, and `superpowers/specs/2026-11-21-grep-content-search-design.md`; plans `superpowers/plans/2026-11-20-ux-1-design-system.md`, `superpowers/plans/2026-11-21-ux-2-chat-surface.md`, `superpowers/plans/2026-11-21-ux-3-contextual-help-structured-editors.md`, `superpowers/plans/2026-11-21-ux-4-data-integrity.md`, `superpowers/plans/2026-11-21-rust-lsp-quiescence.md`, `superpowers/plans/2026-11-21-agents-md-project-instructions.md`, and `superpowers/plans/2026-11-21-grep-content-search.md`. The next cycle is not yet scheduled.

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
| 20 | Loguru sink configuration (console/file, rotation, stdlib) | `specs/2026-11-19-loguru-sinks-design.md` | `plans/2026-11-19-loguru-sinks.md` |
| 21 | Filesystem tools parity (reference toolset + media + hooks) | `specs/2026-11-19-filesystem-tools-design.md` | `plans/2026-11-19-filesystem-tools.md` |
| 22 | Model labels + label-based model routing | `specs/2026-11-19-model-labels-design.md` | `plans/2026-11-19-model-labels.md` |
| 23 | Prompt templating in system prompts + preview | `specs/2026-11-19-prompt-templating-design.md` | `plans/2026-11-19-prompt-templating.md` |
| 24 | Automatic LSP diagnostics (multi-stack + About panel) | `specs/2026-11-19-lsp-diagnostics-design.md` | `plans/2026-11-19-lsp-diagnostics.md` |
| 25 | Session plan tools (TODO-*) | `specs/2026-11-19-plan-tools-design.md` | `plans/2026-11-19-plan-tools.md` |
| 26 | Web search + URL fetch (keyless ddgs/SearXNG) | `specs/2026-11-20-web-search-design.md` | `plans/2026-11-20-web-search.md` |
| 27 | Terminal management + project allowed roots | `specs/2026-11-20-terminal-design.md` | `plans/2026-11-20-terminal.md` |
| 28 | Automatic compaction (usage-driven summaries + context-window recovery) | `specs/2026-11-20-compaction-design.md` | `plans/2026-11-20-compaction.md` |
| 29 | Sub-agent sessions (background children, monitoring, cancellation) | `specs/2026-11-20-subagent-sessions-design.md` | `plans/2026-11-20-subagent-sessions.md` |
| 30 | UX-1 design system + command shell | `specs/2026-11-20-ux-1-design-system-design.md` | `plans/2026-11-20-ux-1-design-system.md` |
| 31 | UX-2 chat surface + runtime UX | `specs/2026-11-21-ux-2-chat-surface-design.md` | `plans/2026-11-21-ux-2-chat-surface.md` |
| 32 | UX-3 contextual help + structured editors | `specs/2026-11-21-ux-3-contextual-help-structured-editors-design.md` | `plans/2026-11-21-ux-3-contextual-help-structured-editors.md` |
| 33 | UX-4 data integrity, errors + navigation states | `specs/2026-11-21-ux-4-data-integrity-design.md` | `plans/2026-11-21-ux-4-data-integrity.md` |
| 34 | D20 AGENTS.md project instructions | `specs/2026-11-21-agents-md-project-instructions-design.md` | `plans/2026-11-21-agents-md-project-instructions.md` |
| 35 | D21 grep content search | `specs/2026-11-21-grep-content-search-design.md` | `plans/2026-11-21-grep-content-search.md` |
| 36 | D19 Rust LSP quiescence readiness | `specs/2026-11-21-rust-lsp-quiescence-design.md` | `plans/2026-11-21-rust-lsp-quiescence.md` |

## Deferred backlog (future evolutions)

Captured ideas, not yet specified. Each will get its own spec → plan → implementation cycle when scheduled. Status = **DEFERRED** unless noted.

| ID | Future evolution | Notes / intended scope |
|---|---|---|
| D3 | **Automatic RAG over `/docs`** | Configurable embedding model; when "RAG on documentation" is opted in, chunk Markdown under the project's `/docs/`, embed into a local vector DB (e.g. Qdrant), and inject retrieved context as a system message immediately after the user message. |
| D5 | **Complex agent workflows** | Move beyond the current ReAct loop: a graphical graph builder with nodes such as post-turn code checks, "ralph mode" re-run completion, and a decision model choosing the next step. |
| D6 | **Duo mode** | Two-agent pairing: the primary receives the user message; the secondary answers the primary's questions. Turns continue automatically until a stop condition is met. |
| D9 | **Automatic session shrinking** | Drop past tool results that are no longer needed; strip multimodal content after a few turns; keep the context lean. |
| D12 | **Agent plugins** | Support the standardized `.agents/plugins/` folder format that mixes skills, MCP configuration, and hooks. Specs at https://agent-plugins.org/ |
| D15 | **Virtual environment / sandboxing** | Opt-in per agent: run tools in a Bashkit environment on a temporary disk, isolating filesystem effects from the real project. |
| D16 | **Telegram / WhatsApp interface** | Let a user create a channel binding (e.g. a Telegram bot) to manage an agent session from a phone: inbound messages start/continue sessions, replies stream back. |
| D17 | **Agile project management** | Integrations with Jira, YouTrack, etc., so agents can create and then consume tickets to manage large projects autonomously. |
| D18 | **Skills page** | A page to add new skills easily, browse the skills.sh registry, and install/manage skills from it. |
