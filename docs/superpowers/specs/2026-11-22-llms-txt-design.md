# D23 — llms.txt Agent Guide Design

**Date:** 2026-11-22
**Status:** Approved
**Backlog item:** D23 (`docs/ROADMAP.md`)

## Goal

Serve a practical, agent-facing Markdown guide to the Agentbox HTTP API at
`/llms.txt`, following the [llmstxt.org](https://llmstxt.org/) convention, with
focused per-section files under `/llms/`. The guide must let an autonomous agent
discover authentication, create the objects it needs, start a session, consume
streamed output, and call the A2A surface without reading the source tree.

## Non-goals

- No generated `llms-full.txt`.
- No per-endpoint JSON schema duplication; exact schemas stay in `/openapi.json`.
- No UI for editing or previewing the guide.
- No admin/feature-flag toggle; the guide is always public.
- No changes to the generated frontend API schema.

## Routes

| Route | Response | Auth |
|---|---|---|
| `GET /llms.txt` | The llmstxt.org index file | Public |
| `GET /llms/{section}.md` | One whitelisted section file | Public |

Both routes set `include_in_schema=False` so `apps/web/openapi.json` and
`src/api/schema.d.ts` do not change.

Responses use `Content-Type: text/markdown; charset=utf-8` and
`Cache-Control: public, max-age=300`.

Unknown section names return `404`. Only names present in a fixed server-side
mapping are served, so no path traversal is possible.

## File layout

Files live in the package so wheels and editable installs behave the same:

```text
packages/agentbox-api/src/agentbox_api/llms/
  llms.txt
  authentication.md
  quickstart.md
  agents.md
  sessions.md
  streaming.md
  protocols.md
  reference.md
```

They are read with `pathlib.Path(__file__).parent / "llms"`, matching the
existing `skills_builtin` pattern in `agentbox_api/skills.py`. Hatchling includes
non-Python files under `src/agentbox_api`.

A new `agentbox_api/routers/llms.py` owns the two routes and the whitelist. It
is registered in `create_app` alongside the existing routers. No authentication
dependency is attached.

## Content outline

All examples use `$AGENTBOX_URL` and `$TOKEN` placeholders and relative paths;
the guide never hard-codes a deployment host. Domain vocabulary follows
`AGENTS.md`: an **agent** is a configuration, a **session** is a live instance,
and a **subagent session** is a child session started by a parent session.

### `llms.txt` — index

- H1 title and a blockquote one-sentence summary.
- A short "Details" paragraph: JSON over HTTP, paths relative to this origin,
  schemas in `/openapi.json`.
- H2 sections with one-line descriptions and links:
  - Getting started: authentication, quickstart.
  - Core concepts: agents, sessions, streaming.
  - Protocols.
  - Reference.
- Optional section linking `/openapi.json` and `/docs`.

### `authentication.md`

- JWT login: `POST /auth/login` body, bearer header, expiry.
- Personal API keys: `POST /api-keys` with `scopes` and optional `expires_at`;
  the raw key is returned once. Keys are sent as `Authorization: Bearer <key>`.
- Scope rules: a key may only request scopes its creator already holds.
- `401` vs `403` distinction and `GET /auth/me`.
- Note that the guide itself is public but every API route is not.

### `quickstart.md`

End-to-end happy path for an agent:

1. Authenticate.
2. Ensure a provider and model exist, or use a model label.
3. Create a project with a server-side directory path.
4. Create an agent configuration.
5. Create a session for that project and agent.
6. Send the first message and consume the stream.
7. Read persisted history.

Each step includes a `curl` request and the important response fields.

### `agents.md`

- `AgentCreate` fields: `name`, `description`, `instructions`,
  `model` XOR `model_label`, `tool_bindings`, `plugin_mcp_bindings`,
  `mode_definitions`.
- Avatar and A2A card endpoints.
- Skills listing and activation through the composer/`skill` request field.
- Prompt templating preview through `POST /prompts/preview`.

### `sessions.md`

- Create/list/get/rename/delete sessions.
- Read history with `GET /sessions/{sid}/messages`.
- Send messages, including `mode`, `skill`, `attachment_ids`, `fork`,
  `fork_from_turn_id`, and `retry_turn_id`.
- Cancel a run with `POST /sessions/{sid}/messages/cancel`.
- Attachments, project file listing, session plan, and LSP snapshot.
- State that subagent sessions are created by the running agent through its
  tools (`start_subagent_session`), not by a public REST endpoint.

### `streaming.md`

- `POST /sessions/{sid}/messages` returns `text/event-stream`.
- Required headers and body fields.
- AG-UI event lifecycle: `RUN_STARTED`, text/reasoning/tool events,
  `RUN_FINISHED`, `RUN_ERROR`, plus the custom `mcp.warning` event.
- Persistence timing: the assistant turn is appended after the run completes.
- Client rules: keep consuming until a terminal event, do not poll history while
  the stream is open, and prefer the cancel endpoint over abandoning the request.

### `protocols.md`

- AG-UI: cross-link to `streaming.md`.
- A2A: card at `GET /a2a/{agent}/.well-known/agent-card.json` and JSON-RPC at
  `POST /a2a/{agent}`. Both require a bearer credential with `sessions:create`
  and a stored agent card, otherwise the dispatcher returns `401`, `403`, or
  `404`.
- ACP: launched over stdio with `agentbox-acp`; not an HTTP endpoint.
- MCP: configured on the agent, not called directly by API clients.

### `reference.md`

- Compact `method | path | permission | purpose` tables grouped by router:
  auth, agents, projects, sessions, prompts, skills, providers, models, labels,
  users, roles, permissions, API keys, plugins, plus `/a2a` and `/sandbox`.
- Error envelope (`{"detail": ...}`), standard status codes (`400`, `401`,
  `403`, `404`, `409`, `422`), and guidance to retry idempotent reads after
  transient failures.
- Link to `/openapi.json` for exact request/response schemas.

## Dev proxy

The Vite dev server must forward the guide URLs to the backend without a prefix
rewrite, so they resolve at the browser origin (`http://localhost:5173`) exactly
as they do in production.

In `apps/web/vite.config.ts`, extend `server.proxy` with:

```ts
"^/llms\\.txt$": {
  target: "http://localhost:8000",
  changeOrigin: true,
},
"^/llms/": {
  target: "http://localhost:8000",
  changeOrigin: true,
},
```

The existing `^/api/` entry stays unchanged and continues to strip `/api`.

## Security

- The guide contains no credentials, tokens, internal paths, or operator data.
- No request body or database content is reflected into the responses.
- Serving is read-only and limited to a fixed filename whitelist.
- The routes bypass auth intentionally, like `/openapi.json`; the documented API
  remains protected by the existing JWT/API-key backend and `require_permission`
  dependencies.

## Testing

Add `packages/agentbox-api/tests/test_llms_txt.py` using the existing
`httpx.ASGITransport` pattern:

- `/llms.txt` returns `200`, `text/markdown`, and starts with an H1.
- Every file name in the server-side whitelist returns `200` with a leading H1.
- Every `](/llms/...)` link in the index resolves to a served file.
- A name outside the whitelist returns `404`; the whitelist itself is the
  traversal guard.
- Both routes work with no `Authorization` header.

Tests are a light drift guard: they do not walk `app.routes`, so new endpoints do
not fail the suite automatically. `reference.md` is kept accurate by review.

## Documentation updates

- `docs/ROADMAP.md`: mark D23 DONE, note the spec/plan, and add the sub-project
  history row.
- `docs/architecture/03-backend.md`: add the public documentation routes to the
  API surface table.
- `docs/architecture/08-frontend.md`: note that the Vite dev proxy also forwards
  `/llms.txt` and `/llms/` without rewriting.
- `docs/architecture/11-testing-and-observability.md`: list the new test file if
  the package test inventory is enumerated there.

## Acceptance criteria

- `GET /llms.txt` returns the index and every linked section returns Markdown.
- The files are readable without credentials and absent from the OpenAPI schema.
- The Vite dev server serves the same URLs on port 5173 without a rewrite.
- The guide documents the real authentication, session, streaming, A2A, and
  reference surface using the canonical domain vocabulary.
- `uv run pytest packages/agentbox-api -q`, `uv run ruff check packages`, and
  `uv run ty check packages` pass.
