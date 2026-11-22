# Protocols

**Scope:** The four protocol surfaces that drive the same agent runtime: AG-UI for the web UI,
ACP for IDEs over stdio, A2A for agent-to-agent calls over HTTP, and MCP for external tools and
resources. Each section describes transport, authentication, event mapping, and lifecycle.

## Shared harness pattern

Every protocol follows the same shape: resolve an `AgentSpec` and model, construct a harness
`Session`, run it, and consume the run's `EventBus`. The protocol adapter maps pydantic-ai and
harness events into its wire format and persists the assistant turn when the run completes.
Protocols differ in transport, authentication, persistence finishing, and process model, not in
agent behavior.

*Figure 1 — Protocol-to-harness mapping.*

```mermaid
flowchart TB
  agui["AG-UI<br/>HTTP SSE"] --> harness
  acp["ACP<br/>stdio JSON-RPC"] --> harness
  a2a["A2A<br/>HTTP JSON-RPC"] --> harness
  harness["Harness + Session"] --> bus["EventBus"]
  bus --> persist["Turn persistence"]
  bus --> map["Protocol event mapping"]
  mcp["MCP toolsets"] --> harness
  map --> aguiOut["AG-UI frames"]
  map --> acpOut["session/update"]
  map --> a2aOut["A2A artifacts"]
```

## AG-UI

The web UI streams a run over server-sent events.

- Endpoint: `POST /sessions/{sid}/messages` returns `text/event-stream`.
- Adapter: `agentbox_api.streaming` wraps the event stream in
  `pydantic_ai.ui.ag_ui.AGUIEventStream` and returns an SSE response.
- Events: pydantic-ai runs are translated into AG-UI event types (`TEXT_MESSAGE_*`,
  `REASONING_MESSAGE_*`, `TOOL_CALL_*`, `RUN_STARTED`, `RUN_FINISHED`, `RUN_ERROR`, and activity
  snapshots).
- Custom events: MCP startup failures are emitted as `CustomEvent` subclasses named
  `mcp.warning`, before run events.
- Persistence: a separate `finish()` task appends the assistant turn when the run outcome is
  known.

*Figure 2 — AG-UI over HTTP.*

```mermaid
sequenceDiagram
  participant W as Web
  participant R as SessionsRouter
  participant H as Harness
  participant B as EventBus
  participant G as AGUIEventStream
  participant L as LLM

  W->>R: POST /sessions/{sid}/messages
  R->>H: run
  H->>L: run_stream_events
  loop streamed events
    L-->>H: event
    H->>B: RunEvent
    B-->>G: event
    G-->>W: AG-UI SSE frame
  end
  H-->>R: RunOutcome
  R-->>W: RUN_FINISHED
```

## ACP

ACP lets an external IDE drive sessions over stdin/stdout JSON-RPC.

- Entry points: the `agentbox-acp` console script and `python -m agentbox_api.acp_server`.
- Server: `AgentboxAcpAgent` implements initialize, new/load/resume/delete/close session, prompt,
  cancel, and set-mode.
- Session cache: per process, keyed by ACP session id, holding the spec, model, registry, mode,
  active run, and extra roots.
- Prompt flow: build a harness `Session` from the latest leaf, run the harness, map events with
  `update_for_event` into `session/update` payloads, then append the assistant turn.
- MCP: ACP clients may supply stdio MCP servers; `_with_servers` adds them to the spec.
- Shutdown: `close_session` closes MCP toolsets, kills terminal jobs, recursively cancels
  descendant subagent sessions, and cancels the active run.
- Persistence: the same SQLite database as HTTP; the ACP process opens its own engine.

*Figure 3 — ACP over stdio.*

```mermaid
sequenceDiagram
  participant I as IDE
  participant A as ACP adapter
  participant H as Harness
  participant D as DB
  participant M as MCP

  I->>A: initialize
  I->>A: new_session(cwd)
  A->>D: resolve/create project and session
  I->>A: prompt
  A->>M: start supplied servers if any
  A->>H: run
  loop streamed events
    H-->>A: event
    A-->>I: session/update
  end
  A->>D: append assistant turn
  A-->>I: PromptResponse
  I->>A: close_session
  A->>M: close toolsets
```

## A2A

A2A exposes selected agents to other agents or services.

- Mount: `app.mount("/a2a", A2ADispatcher(...))`.
- Routing: the dispatcher strips `/a2a`, parses `/{agent_name}/...`, authenticates, checks
  `sessions:create`, and requires a stored `AgentCard` (otherwise 404).
- Per-agent app: a lazily created Starlette app using `DefaultRequestHandler` with
  `InMemoryTaskStore`, plus agent-card and JSON-RPC routes.
- Card: `build_card` parses the stored JSON, forces streaming, and rewrites
  `supported_interfaces` to `{a2a_public_url}/a2a/{agent_name}`.
- Execution: `AgentboxA2AExecutor` maps `task.context_id` to an Agentbox session id, works under
  `a2a_workspace`, streams text into artifacts, and completes or fails the task.
- Cancellation: the executor cancels the run tracked for that context id.

*Figure 4 — A2A over HTTP.*

```mermaid
sequenceDiagram
  participant C as Caller
  participant D as A2ADispatcher
  participant A as Per-agent app
  participant E as Executor
  participant H as Harness
  participant DB as DB

  C->>D: GET /{agent}/.well-known/agent-card.json
  D->>DB: load agent + card
  D-->>C: agent card
  C->>D: POST /{agent} JSON-RPC
  D->>D: authenticate + sessions:create
  D->>A: delegate
  A->>E: execute(message, context_id)
  E->>DB: ensure project and session
  E->>H: run
  H-->>E: streamed events
  E-->>C: artifacts + task status
```

## MCP

MCP supplies external tools and resources. Agentbox supports two binding types.

**Remote URL (streamable HTTP).** The toolset is constructed on every agent build and is not
cached by the session manager. It is ephemeral and reconnects as needed.

**stdio.** A local process is started from `command`, `args`, `env`, and `cwd`. These processes
are expensive, so they are session-scoped:

- `McpSessionManager` is a process-global singleton.
- Toolsets are cached per Agentbox session id, behind a per-session `asyncio.Lock`.
- All servers for a session start concurrently with a configured start timeout.
- A failed server produces a `McpWarning` instead of failing the turn.
- `sweep_idle(ttl)` closes sessions that have not been used recently; the app lifespan runs it on
  an interval.
- `close_session` and `close_all` exit toolsets; they are called on session deletion, ACP close,
  and app shutdown.

*Figure 5 — MCP stdio toolset lifecycle.*

```mermaid
sequenceDiagram
  participant H as Harness
  participant SM as McpSessionManager
  participant T as StdioTransport
  participant S as MCP server
  participant W as Sweeper

  H->>SM: toolsets_for(session_id, bindings)
  SM->>SM: acquire per-session lock
  SM->>T: start each server
  T->>S: spawn + initialize
  alt all servers ready
    S-->>SM: toolsets
  else partial failure
    S-->>SM: warnings + ready toolsets
  end
  SM-->>H: toolsets (+ warnings)
  H->>SM: toolsets_for again
  SM-->>H: cached toolsets
  W->>SM: sweep_idle(ttl)
  SM->>T: exit idle sessions
```

### MCP Apps

MCP servers can return app content that the UI renders in a sandboxed iframe. The backend is the
only network path for the app: the web client posts to
`POST /sessions/{sid}/mcp/{server_id}/resources/read` and `/tools/call`, and the backend reuses
the session's cached stdio toolset or opens an ephemeral remote toolset. `/sandbox` serves the
proxy page and computes its CSP.

## Protocol comparison

| Protocol | Transport | Auth | Persistence | Lifecycle | Concurrency |
|---|---|---|---|---|---|
| AG-UI | HTTP SSE | Bearer JWT or API key | Same process as API | Per-request stream; run tracked by session | One active run per session |
| ACP | stdio JSON-RPC | Local process; optional MCP servers from client | Own engine, same database | Per-process session cache | One run per ACP session |
| A2A | HTTP JSON-RPC | Bearer JWT or API key with `sessions:create` | Same process as API; in-memory task store | Per-agent app cached in dispatcher | Runs tracked per context id |
| MCP | HTTP or stdio | Provider/process environment | Toolset lives for the session | Session-scoped cache with idle sweep | Per-session lock; concurrent start |

## Implementation notes

> **Implementation note:** stdio MCP bindings are captured when a session's toolsets start.
> Editing an agent's MCP bindings does not restart toolsets for an existing session; they are
> reused until the session is closed or idle-swept.

> **Implementation note:** A2A task state is in memory. A restart loses A2A task bookkeeping but
> keeps the Agentbox sessions and turns.

> **Implementation note:** the frontend parses the AG-UI SSE stream itself. `@ag-ui/client` is a
> dependency, but the client's agent abstraction is not used.

## Related

- [Harness and runtime](04-harness-runtime.md)
- [Backend](03-backend.md)
- [Auth and security](06-auth-and-security.md)
- [Concurrency and lifecycle](10-concurrency-and-lifecycle.md)
- [Index](README.md)
