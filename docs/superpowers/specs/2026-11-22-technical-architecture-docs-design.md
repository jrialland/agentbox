# Technical Architecture Documentation Set - Design Specification

## 1. Context and Scope

### 1.1 What this sub-project encompasses

A new, maintainer-oriented technical documentation set under `docs/architecture/`. It describes
the implemented system from an architecture point of view: the technology stack, package and
process topology, backend and frontend structure, data model, protocol adapters, runtime and
concurrency behavior, and test/observability surfaces. All diagrams are authored in Mermaid.

The existing documentation is product- and feature-oriented:

- `README.md` is the product overview and quick start.
- `docs/initial_spec.md` is the original product specification.
- `docs/ROADMAP.md` maps requirements to implementation status.
- `docs/superpowers/specs/` and `docs/superpowers/plans/` are per-feature design/plan pairs.
- `docs/reviews/` holds UX review reports and screenshots.

There is no single place that explains how the system fits together for someone maintaining it.
This set fills that gap without duplicating those sources.

### 1.2 Boundaries (out of scope)

- End-user or operator guides, installation tutorials, and deployment recipes.
- Regenerating or hand-editing API reference artifacts (`openapi.json`,
  `apps/web/src/api/schema.d.ts`). The docs link to and summarize them; they never restate the
  full schema.
- Rewriting or replacing the per-feature specs/plans or `ROADMAP.md`.
- Proposing architectural changes. The set documents current behavior and calls out
  implementation quirks explicitly; it is not a redesign.
- Marketing or visual-design documentation. The UX-1 design-system spec remains the authority
  for visual direction; the frontend doc only summarizes how the design system is structured.

### 1.3 Dependencies

- No new runtime or build dependencies. Documentation is plain Markdown with Mermaid code fences.
- Mermaid must render on GitHub and in VS Code's Markdown preview; use only syntax supported by
  both.
- Content must match the code at the time of writing. Where the code and older docs disagree,
  the code wins and the discrepancy is noted.

## 2. Decisions and Rationale

### 2.1 Audience: maintainers and architects

The primary reader is a developer who must change the system: a new maintainer onboarding, an
architect reviewing boundaries, or a contributor adding a protocol or chat feature. The docs
assume programming competence and some familiarity with the framework names, but not prior
knowledge of Agentbox internals. Every claim should be reachable from a file path.

### 2.2 Organization: layered by runtime concern (Approach A)

Three approaches were considered:

- **A. Layered by runtime concern (chosen).** An index plus docs split by concern (stack,
  backend, harness, data, auth, protocols, frontend, chat, lifecycle, testing). Each file owns
  one concern, carries its own diagrams, and cross-links.
- **B. C4-level split** (context → containers → components → code). Standard, but it conflicts
  with the requested stack/backend/frontend framing and scatters frontend and backend across
  levels.
- **C. Fewer large documents.** Fewer files, but long, harder to navigate, and staler faster.

A was chosen because maintainers navigate by the concern they are changing. C4 diagrams are
still used inside the index and overview where they add value, rather than as the organizing
principle.

### 2.3 Diagrams: Mermaid only

Mermaid renders on GitHub and VS Code, is diff-friendly, and expresses sequence, flow, state, and
ER diagrams semantically. No binary diagram assets are introduced. `C4Context`/`C4Container`
Mermaid diagrams are used for the system/container view; `flowchart`, `sequenceDiagram`,
`stateDiagram-v2`, and `erDiagram` cover the rest.

### 2.4 Document current behavior, including quirks

The set is a reference for maintainers, so it must be trustworthy. It documents the system as
implemented, including known quirks, marked as **Implementation note** callouts. Examples found
during research that must be reflected:

- `SessionRow.head_turn_id` is effectively legacy; the session leaf is derived from `TurnRow`
  parent links.
- A2A task state is in memory (`InMemoryTaskStore`), so A2A tasks do not survive a restart while
  Agentbox sessions do.
- The frontend parses the AG-UI SSE stream with a custom parser; `@ag-ui/client` is a dependency
  but the client abstractions are not used.
- The `mitt` event bus in `src/lib/bus.ts` is declared but currently has no production publisher
  or subscriber.
- Permission checks are not route guards; navigation is filtered in the shell while the backend
  remains the authorization boundary.
- There are no ORM relationships or DB cascades; deletion is explicit in `delete_session_data`.

### 2.5 Avoid duplication and staleness

Each fact has one home. The README, product spec, roadmap, and per-feature specs remain
authoritative for their topics; the architecture docs summarize and link. Generated artifacts are
never reproduced. Each document lists the source files it is responsible for so drift is
detectable.

## 3. Deliverables

All files live under `docs/architecture/`.

```
docs/architecture/
  README.md
  01-system-overview.md
  02-tech-stack.md
  03-backend.md
  04-harness-runtime.md
  05-data-model.md
  06-auth-and-security.md
  07-protocols.md
  08-frontend.md
  09-chat-and-streaming.md
  10-concurrency-and-lifecycle.md
  11-testing-and-observability.md
  12-glossary-and-decisions.md
```

### 3.1 `README.md` — index and reading map

- Purpose of the set and its relationship to existing docs.
- System-at-a-glance paragraph and a C4 context diagram.
- C4 container diagram covering web app, API, SQLite, LLM providers, MCP servers, ACP host, and
  A2A callers.
- Reading paths:
  - New maintainer: 01 → 02 → 03 → 04 → 05.
  - Protocol work: 07 → 04 → 10.
  - Frontend work: 08 → 09 → 02.
  - Change-impact lookup: 12 → target doc.
- Table of contents linking every document.
- A "source of truth" table pointing to README, initial spec, ROADMAP, and specs/plans.

### 3.2 `01-system-overview.md` — system and decisions

- Intent and guiding constraints (protocol compliance, local-first/self-hosted, async, UI
  ambition) with their consequences.
- Runtime topology: browser, Vite dev proxy, FastAPI/uvicorn, SQLite, model providers, MCP
  servers, ACP host, A2A callers.
- Package dependency direction and the rule that dependencies point downward, including the
  intentional upward coupling from `agentbox-models` repositories into harness domain types.
- The "no module-level FastAPI app" rule and the `create_app(Settings(...))` composition root.
- A summary table of cross-cutting architectural decisions and trade-offs (turn-chain history,
  protocol adapters over a shared harness, session-scoped MCP processes, scope-based auth,
  JSON-text columns for agent definitions). Each links to the detailed doc and relevant spec.
- Diagrams: package dependency graph, runtime/deployment topology.

### 3.3 `02-tech-stack.md` — stack and tooling

- Backend stack table: Python 3.11, uv workspace, FastAPI/uvicorn, Starlette authentication,
  SQLModel/SQLAlchemy async + aiosqlite, Alembic, pydantic-settings, pydantic-ai (with AG-UI),
  agent-client-protocol, a2a-sdk, MCP, loguru, bcrypt/PyJWT, Pillow/robohash, Jinja2, pytest +
  pytest-asyncio + pytest-timeout, Ruff, ty, bandit.
- Frontend stack table: React 19, Vite 8, TypeScript strict, Mantine 9, TanStack Query 5,
  Zustand 5, React Router 7, `openapi-fetch`/`openapi-typescript`, `@ag-ui/core`,
  `@mcp-ui/client`, `react-markdown`/`remark-gfm`, `highlight.js`, `mermaid`,
  `react-zoom-pan-pinch`, `mitt`, RemixIcon, fonts.
- Tooling and pipelines: Vite proxy (`/api` → port 8000, prefix stripped), openapi generation
  (`gen-openapi.py` → `codegen`), Vitest vs Playwright vs Storybook, `just` tasks, test packaging
  constraints (one pytest invocation per package, 60s timeout).
- Why each notable dependency exists, in one line.
- Diagrams: build/generation pipeline and local dev request flow.

### 3.4 `03-backend.md` — FastAPI application

- `agentbox-api` module map: app factory, config, deps, security, auth backend, runs, runtime,
  streaming, activity, skills, plan tools, project instructions, templating, MCP relay,
  sub-sessions, sandbox, avatars, logging, dev server/seed, protocol adapters.
- `create_app` composition: engine/session factory, lifespan startup/shutdown, middleware order
  (authentication, CORS), router registration, `/sandbox`, `/a2a` mount, `app.state`.
- API surface: router prefix/tag table with responsibilities and important endpoints.
- Chat turn request flow across `routers/sessions.py`, `runtime.py`, `skills.prepare_agent`,
  `harness`, `streaming.py`, and persistence.
- Configuration: `Settings` fields grouped by concern, env-var mapping, `.env`, DB URL, JWT
  requirements.
- Logging: loguru sinks, stdlib interception, the no-stdout rule for ACP.
- Error model: HTTP exceptions, `normalize_error`, `RunOutcome`, cancellation, `ApiError`
  mapping on the client.
- Implementation notes: one active run per session keyed by session id; final persistence runs in
  a separate task and can be interrupted on client disconnect.
- Diagrams: middleware chain, router map, HTTP turn sequence.

### 3.5 `04-harness-runtime.md` — agent runtime

- `agentbox-harness` module map and its isolation from HTTP/DB.
- Domain model: `AgentSpec`, `ModelBinding`, `Mode`, `ToolBinding`, `NativeToolBinding`,
  `McpToolBinding`, default `ask`/`agent` modes.
- `Session` and the parent-linked turn chain; `MessageLogStore`, in-memory and SQLite stores;
  summary turns.
- `RunManager`, `Run`, `CancellationToken`, `EventBus` (replay history, subscriber queues,
  closing).
- `Harness` responsibilities: `start_session`, `run`, `run_turn`, MCP preparation, mode
  resolution.
- `build_agent`: native tool selection by mode flags, sub-agent tools, sub-session tools, remote
  MCP toolsets, pre-started stdio toolsets.
- Middleware pipeline and compaction (token estimate, trigger ratio, summary insertion, overflow
  recovery and one retry).
- Sub-agents versus sub-sessions (in-process delegated tool vs background child session).
- Tool registry and toolboxes: filesystem (root/extra-root sandboxing, media), grep, terminal job
  manager, web search/fetch.
- LSP: stack detection, manager singletons, diagnostics hook, quiescence.
- Diagrams: agent assembly, run/event flow, mode-based tool selection.

### 3.6 `05-data-model.md` — persistence

- ERD for all core and auth tables with keys and foreign keys.
- Table-by-table reference: core tables (Provider, Model, Label, ModelLabelLink, Agent,
  AgentCard, Project, SessionRow, PlanItem, TurnRow, SessionAttachment) and auth tables
  (User, Role, Permission, RolePermissionLink, UserRoleLink, ApiKey).
- Column encoding rules: real JSON (`extra_roots`, `activity`, `attachments`), JSON-encoded text
  (`tool_bindings`, `mode_definitions`, `sub_agent_ids`, `card`, `scopes`), and binary
  (`avatar_data`, attachment `data`).
- Turn chain: `parent_id` (not an FK), leaf derivation, fork/retry semantics, summary rewiring.
- Deletion semantics: explicit cascade in `delete_session_data`, project deletion behavior.
- Migrations: dev server `create_all` + seed versus Alembic for real schema evolution; migration
  list.
- Implementation notes: no ORM relationships or DB cascades; `head_turn_id` is legacy; API key
  hashes and avatar storage.
- Diagrams: ERD, turn-chain graph.

### 3.7 `06-auth-and-security.md` — identity and authorization

- RBAC model: users → roles → permissions, link tables, permission string format.
- Authentication middleware: `JWTAuthenticationBackend`, JWT path, API-key fallback, effective
  scopes, `is_active` behavior.
- `require_permission` dependency pattern and how routers use it.
- Token issuance: login flow, bcrypt passwords, HS256 JWT with expiry.
- API keys: generation, one-time display, SHA-256 hashing, scope-subset validation, expiry and
  revocation.
- A2A auth: authenticated user plus `sessions:create` scope; context variable propagation.
- Sandboxing and guardrails: project root/extra-root path resolution, MCP app CSP/proxy,
  web-fetch SSRF and redirect revalidation, attachment handling.
- Security notes and known limitations (plaintext provider API keys, no `is_active` enforcement
  in auth, dev JWT fallback in ACP).
- Diagrams: authentication decision flow, RBAC graph.

### 3.8 `07-protocols.md` — protocol adapters

- The shared pattern: every protocol drives the same `Harness` + `EventBus` and persists turns,
  with protocol-specific event mapping and lifecycle.
- AG-UI: `AGUIEventStream`, SSE response, event mapping, custom MCP warning events.
- ACP: `agentbox-acp` / `python -m agentbox_api.acp_server`, stdio JSON-RPC, session lifecycle
  (new/load/resume/prompt/cancel/mode/close), ACP-supplied MCP servers, event → `session/update`
  mapping.
- A2A: mount and dispatcher, per-agent app caching, agent cards, JSON-RPC, API-key auth,
  executor mapping `context_id` to an Agentbox session, in-memory task store.
- MCP: remote URL toolsets (ephemeral, per agent build) versus stdio toolsets (session-scoped,
  LRU-ish idle sweep, per-session lock, concurrent start with timeout, failures as warnings),
  binding capture semantics, MCP Apps relay through the backend.
- Protocol comparison table: transport, auth, persistence, lifecycle, concurrency.
- Diagrams: sequence diagram per protocol, protocol-to-harness mapping.

### 3.9 `08-frontend.md` — React application

- Build and tooling: Vite config and proxy, TypeScript strictness and relative imports, env
  vars, Storybook, Vitest, Playwright, generated schema.
- Provider stack and routing tree, `RequireAuth`, `CommandShell`, 3-pane desktop shell and
  mobile behavior, `Workspace`/`PageContainer`.
- API layer: typed `openapi-fetch` client, auth middleware, 401 handling, raw-fetch multipart
  paths, endpoint façade, error normalization, retry policy, query keys and invalidation.
- State: Zustand auth store (session storage), TanStack Query cache, local state, and the
  currently unwired event bus.
- Design system: layering (tokens → theme → primitives → patterns → shell), theming and
  dark-first behavior, Mantine integration, CSS layers/modules, key components and conventions
  (Icon/IconButton labels).
- Pages: each page's responsibility and the backend APIs it calls.
- Help and onboarding: help registry/drawer/tips, onboarding wizard and checklist, storage keys.
- Diagrams: provider tree, route tree, data-flow diagram (page → query → API → backend).

### 3.10 `09-chat-and-streaming.md` — chat subsystem

- AG-UI client lifecycle in `useChat`/`agent.ts`: custom SSE parsing, request body fields,
  run status transitions, cancellation, stream-end finalization.
- Event-to-segment reducer: ordered live segments (text, reasoning, tool, app), ID fallbacks,
  finalization rules, error handling.
- Rendering: persisted `MessageTurn` vs live segments, optimistic pending user turn, summary
  notices, activity chips, plan panel, token usage, auto-scroll and jump-to-latest.
- Persistence and reload: server-authoritative history, refresh/invalidation, what is and is not
  rehydrated (live segments and app tabs are not).
- Edit/fork, retry, stop semantics and the request fields they produce.
- Composer: mode switching, attachments upload/download, file mentions, skills slash menu,
  speech-to-text.
- MCP apps: activity snapshot to tab, `AppRenderer`, backend relay calls, split view and mobile
  drawer.
- Markdown, code highlighting, and Mermaid: complete-fence detection, fallback, zoom/pan/copy/
  fullscreen.
- Diagrams: stream sequence, segment state machine.

### 3.11 `10-concurrency-and-lifecycle.md` — runtime behavior

- Lifespan timeline: logging/LSP configuration, MCP start timeout, idle sweep task, sub-session
  reconciliation, shutdown order.
- Run model: one `asyncio.Task` per turn, `RunRegistry` keyed by session, cancellation path, the
  separate persistence task.
- Per-run `EventBus` semantics and the two-consumer pattern.
- Sub-sessions: concurrency and depth caps, child status persistence, cancellation, restart
  reconciliation, module-global tracking.
- MCP lifecycle: session-scoped process cache, lock, idle TTL, sweep interval, binding-capture
  caveat, shutdown.
- Global singletons: LSP manager (per project/stack, backoff, no idle eviction), terminal job
  manager (per-session jobs, process-tree kill).
- Cross-protocol cleanup coupling: `delete_session_data`, ACP close, app shutdown; idempotency.
- Project-instruction state and avatar caches.
- Diagrams: lifespan timeline, run/cancel state machine, MCP session lifecycle.

### 3.12 `11-testing-and-observability.md` — verification and insight

- Test strategy per package: harness, models, providers, api; self-skipping external integration
  tests; timeout rules; one-package-per-invocation constraint.
- Frontend testing: Vitest with jsdom and shared render helper, Playwright e2e harness (stub
  servers on 9000/9999, backend on 8000, Vite on 5173, DB/skills reset), Storybook as the visual
  review surface.
- Generated-artifact workflow and checks (`ruff`, `ty`, build, package tests).
- Logging: sinks, rotation/retention/compression, stdlib interception, `log_exception`.
- Runtime observability surfaces: activity collection and persistence, token/context usage,
  plan endpoint, LSP status endpoint, MCP warnings, run outcomes.
- Known gaps/quirks surfaced elsewhere (ACP JWT fallback, in-memory A2A tasks, unused bus).
- Diagrams: test pyramid, observability data flow.

### 3.13 `12-glossary-and-decisions.md` — reference

- Glossary of domain and protocol terms (agent, mode, native tool, MCP binding, session, turn,
  branch/fork, sub-agent, sub-session, compaction, run, activity, agent card, ACP/A2A/AG-UI/MCP,
  RBAC, API key, extra roots).
- Decision log: short ADR-style entries (context → decision → consequences → source spec).
- "Where to change X" map: task → files → owning doc.

## 4. Conventions

- One H1 per file; numbered section headings; a short "Scope" paragraph at the top.
- Mermaid diagrams in fenced blocks with a one-line caption above.
- Code references as `path/to/file.py:line`; spec references as relative links into
  `docs/superpowers/`.
- Use **Implementation note** blockquotes for behavior that is surprising, legacy, or a known
  limitation.
- Prefer tables for inventories (routers, settings, stack, tables, events) and prose for flows.
- Cross-link at the end of each document ("Related") using relative paths.
- No absolute local paths, no machine-specific output, no secrets or example keys.
- Keep each document scoped to its concern; link instead of repeating detail.

## 5. Diagram Inventory

| Diagram | Type | Home |
|---|---|---|
| System context | `C4Context` | README |
| Container topology | `C4Container` | README |
| Package dependency graph | `flowchart` | 01 |
| Runtime/deployment topology | `flowchart` | 01 |
| Build/generation pipeline | `flowchart` | 02 |
| Local dev request flow | `flowchart` | 02 |
| Middleware chain | `flowchart` | 03 |
| Router map | `flowchart` | 03 |
| HTTP chat turn | `sequenceDiagram` | 03 |
| Agent assembly | `flowchart` | 04 |
| Run/event flow | `sequenceDiagram` | 04 |
| Mode-based tool selection | `flowchart` | 04 |
| ERD | `erDiagram` | 05 |
| Turn chain | `flowchart` | 05 |
| Authentication decision flow | `flowchart` | 06 |
| RBAC graph | `flowchart` | 06 |
| AG-UI sequence | `sequenceDiagram` | 07 |
| ACP sequence | `sequenceDiagram` | 07 |
| A2A sequence | `sequenceDiagram` | 07 |
| MCP/stdio sequence | `sequenceDiagram` | 07 |
| Protocol-to-harness mapping | `flowchart` | 07 |
| Provider tree | `flowchart` | 08 |
| Route tree | `flowchart` | 08 |
| Frontend data flow | `flowchart` | 08 |
| Chat stream sequence | `sequenceDiagram` | 09 |
| Segment state machine | `stateDiagram-v2` | 09 |
| Lifespan timeline | `sequenceDiagram` | 10 |
| Run/cancel state machine | `stateDiagram-v2` | 10 |
| MCP session lifecycle | `stateDiagram-v2` | 10 |
| Test pyramid | `flowchart` | 11 |
| Observability data flow | `flowchart` | 11 |

## 6. Acceptance Criteria

1. Every file in section 3 exists and is linked from `docs/architecture/README.md`.
2. Every diagram listed in section 5 exists in its home file and uses valid Mermaid that renders
   in GitHub and VS Code.
3. Every package, router, table, protocol adapter, and major frontend module has a named home
   document and a code reference.
4. The package dependency direction, ERD, API surface, and chat turn flow match the code.
5. Known quirks listed in section 2.4 are documented as implementation notes in the appropriate
   files.
6. No file duplicates the full OpenAPI schema, the product spec, or existing per-feature specs;
   they link instead.
7. Markdown is clean: no broken relative links, no absolute local paths, no placeholders such as
   TBD/TODO, no secrets.
8. `docs/ROADMAP.md` gains a row or note recording this documentation sub-project.

## 7. Verification

- Render-check all Mermaid blocks (GitHub preview or `mermaid-cli` if available) and fix syntax.
- Walk the repo tree and confirm each documented module/source path exists.
- Cross-check the ERD, router table, Settings fields, and package dependency list against
  `tables/`, `routers/`, `config.py`, and each `pyproject.toml`.
- Link-check relative Markdown links.
- Manually execute one reading path (new maintainer) to confirm it explains how a chat request
  flows end to end.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Docs drift from code quickly | Per-file source lists, implementation notes, and links to specs; keep inventories table-based for easy diffing. |
| Duplication with existing specs | Summarize and link; do not restate. |
| Mermaid syntax renders on one viewer but not another | Use conservative, widely supported syntax; render-check. |
| Over-documenting transient quirks | Mark them as implementation notes, not as intended design. |
| Scope creep into redesign | Document current behavior; architectural changes go through their own spec. |

## References

- `README.md` — product overview and repository layout.
- `docs/initial_spec.md` — original product specification.
- `docs/ROADMAP.md` — requirement coverage and sub-project history.
- `docs/superpowers/specs/` — per-feature design specifications.
- `docs/superpowers/specs/2026-11-20-ux-1-design-system-design.md` — visual/design-system authority.
