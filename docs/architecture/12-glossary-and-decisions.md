# Glossary, Decisions, and Change Map

**Scope:** Reference material: domain and protocol terms, the architecture decision log, and a
lookup from a maintenance task to the files to start with.

## Glossary

| Term | Definition | Where |
|---|---|---|
| Agent | A configuration: system prompt, tools, model, and optional modes. Not a live unit | [04](04-harness-runtime.md) |
| `AgentSpec` | The harness's canonical agent definition; persisted as an `Agent` row | [04](04-harness-runtime.md) |
| Mode | A named capability set; `ask` is read-only, `agent` enables writes | [04](04-harness-runtime.md) |
| Native tool | A built-in Python tool (filesystem, grep, terminal, web, plan) | [04](04-harness-runtime.md) |
| MCP binding | A remote URL or stdio MCP server attached to an agent | [07](07-protocols.md) |
| Session | An agent bound to a project, with a persisted conversation | [05](05-data-model.md) |
| Turn | One `user`, `assistant`, or `summary` message in a session | [05](05-data-model.md) |
| Turn chain | The parent-linked list of turns that defines history and branches | [05](05-data-model.md) |
| Branch / fork | A new turn whose parent is an earlier turn, leaving the old suffix unreachable | [09](09-chat-and-streaming.md) |
| Retry | Re-running an assistant turn without duplicating its user turn | [09](09-chat-and-streaming.md) |
| Subagent | The agent configuration selected by a parent session for a subagent session | [04](04-harness-runtime.md) |
| Subagent session | A background session spawned by a parent session, with its own row, status, live output, and final output | [10](10-concurrency-and-lifecycle.md) |
| Compaction | Summarizing older turns when context usage approaches the window | [04](04-harness-runtime.md) |
| Summary turn | The turn that replaces a compacted prefix in the chain | [05](05-data-model.md) |
| Run | One execution of an agent, owning a task and event stream | [04](04-harness-runtime.md) |
| Activity | Persisted summary of reasoning, tool calls, and timings for a turn | [11](11-testing-and-observability.md) |
| `RunOutcome` | Normalized run result: success, cancelled, or an error | [03](03-backend.md) |
| AG-UI | Event protocol for streaming an agent run to the web UI | [07](07-protocols.md) |
| ACP | Agent Client Protocol; JSON-RPC over stdio for IDE integration | [07](07-protocols.md) |
| A2A | Agent-to-Agent protocol; cards plus JSON-RPC over HTTP | [07](07-protocols.md) |
| Agent card | The A2A metadata document that exposes an agent | [07](07-protocols.md) |
| MCP | Model Context Protocol; external tools and resources | [07](07-protocols.md) |
| MCP App | Server-provided UI rendered in a sandboxed iframe and proxied by the backend | [07](07-protocols.md) |
| RBAC | Users hold roles; roles hold permissions | [06](06-auth-and-security.md) |
| Permission scope | A `resource:action` string checked by `require_permission` | [06](06-auth-and-security.md) |
| API key | A scoped, optionally expiring credential derived from a user | [06](06-auth-and-security.md) |
| Extra roots | Additional filesystem roots a project's tools may access | [05](05-data-model.md) |
| Model label | A routing label that resolves to the best linked model | [05](05-data-model.md) |
| Project instruction | `AGENTS.md` content injected into the system prompt | [03](03-backend.md) |

## Decision log

| ID | Decision | Context | Consequences | Source |
|---|---|---|---|---|
| AD-1 | Drive every protocol through one harness | Four protocol surfaces share agent behavior | Adapters stay thin but must map events and lifecycles | [07](07-protocols.md) |
| AD-2 | Persist history as a parent-linked turn chain | Fork, retry, and compaction must be structural | Reads walk the chain; no ORM relationships or cascades | [05](05-data-model.md) |
| AD-3 | Local-first database with SQLite default and PostgreSQL/MySQL/MariaDB support | Self-hosted operation with no control plane; operators can choose a network database | Network databases need separate backup/operation; process-local state still does not survive restart | [01](01-system-overview.md) |
| AD-4 | Async throughout | Streaming, MCP, LSP, and terminals are concurrent | Careful lifecycle and cleanup coupling is required | [10](10-concurrency-and-lifecycle.md) |
| AD-5 | Session-scoped stdio MCP processes | Server startup is expensive | Bindings are captured at start; edits need a session restart or sweep | [07](07-protocols.md) |
| AD-6 | Scope-based auth with JWT and API keys | Users and automation need different credentials | One permission check covers HTTP and A2A; UI is not a boundary | [06](06-auth-and-security.md) |
| AD-7 | Store agent bindings, modes, project roots, API-key scopes, and activity in normalized tables | Relational portability and FK integrity | Adding new binding/mode fields requires a migration | [05](05-data-model.md) |
| AD-8 | Custom SSE parsing on the web | The AG-UI client abstraction did not fit the UI's segment model | The app owns framing and segment reduction | [09](09-chat-and-streaming.md) |
| AD-9 | No route-level permission guards | The backend is the authorization boundary | Hidden nav items can still be reached by URL and are rejected server-side | [08](08-frontend.md) |
| AD-10 | Explicit cascade deletion | No database cascades exist | All session-owned resources must be cleaned in `delete_session_data` | [10](10-concurrency-and-lifecycle.md) |

## Where to change X

| Task | Start here | Owning doc |
|---|---|---|
| Add an HTTP route | Create a router in `packages/agentbox-api/src/agentbox_api/routers/`, include it in `create_app` | [03](03-backend.md) |
| Add a native tool | Add a function to `agentbox-harness/src/agentbox_harness/tools/`, register it in the tool registry and catalog | [04](04-harness-runtime.md) |
| Add a provider kind | Extend `agentbox_providers.resolver.resolve_model` and the provider form presets | [04](04-harness-runtime.md), [08](08-frontend.md) |
| Change the data model | Edit `tables/core.py` or `tables/auth.py`, then add an Alembic migration | [05](05-data-model.md) |
| Add or change a protocol event mapping | Edit `streaming.py`, `acp_server.py`, or `a2a_executor.py` | [07](07-protocols.md) |
| Add a page | Create it under `apps/web/src/pages/`, add a route in `App.tsx`, add nav in `CommandShell` | [08](08-frontend.md) |
| Change chat rendering | Edit `SessionPage.tsx`, `MessageTurn.tsx`, `MarkdownBlock.tsx`, or `segments.ts` | [09](09-chat-and-streaming.md) |
| Change authentication or authorization | Edit `auth_backend.py`, `deps.py`, or `security.py` | [06](06-auth-and-security.md) |
| Change MCP behavior | Edit `tools/mcp.py`, `tools/mcp_session.py`, or `mcp_relay.py` | [07](07-protocols.md) |
| Change logging | Edit `agentbox_api/logging.py` and the logging fields in `config.py` | [03](03-backend.md), [11](11-testing-and-observability.md) |
| Change the shell or design tokens | Edit `design-system/tokens/tokens.css`, `theme/theme.ts`, or `shell/` | [08](08-frontend.md) |
| Add contextual help | Add a `HelpId` in `help/types.ts` and an entry in `help/content.ts` | [08](08-frontend.md) |
| Change test infrastructure | Edit `apps/web/playwright.config.ts`, `e2e/prepare.ts`, or package pytest settings | [11](11-testing-and-observability.md) |

## Related

- [Index](README.md)
- [System overview](01-system-overview.md)
- [Roadmap](../ROADMAP.md)
