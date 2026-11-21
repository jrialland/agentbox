# Harness and Runtime

**Scope:** `agentbox-harness` is the pure agent runtime. It knows nothing about HTTP or the
database. This document covers its domain model, session and run mechanics, event bus,
middleware, compaction, sub-agents, tool boxes, and LSP integration.

## Domain model

An agent definition is an `AgentSpec`. It is the harness's stable contract; the API layer
serializes it into database rows and back.

| Type | Purpose |
|---|---|
| `AgentSpec` | Name, description, instructions, model binding, tool bindings, modes, sub-agent ids |
| `ModelBinding` | The model selected for the agent |
| `Mode` | A named behavior mode with flags such as `write` |
| `NativeToolBinding` | A reference to a built-in tool by name |
| `McpToolBinding` | A remote URL or stdio MCP server binding |
| `ToolBinding` | Union of native and MCP bindings |
| `DEFAULT_MODES` | `ask` (read-only) and `agent` (write-enabled) |

Modes are the primary capability switch. `ask` exposes read-only tools; `agent` additionally
enables write tools, terminal access, and sub-session tools. Tool registry entries declare the
flags they require, and `select_tools(mode, names)` filters accordingly.

## Sessions and the turn chain

A `Session` wraps a `MessageLogStore` and a head id. History is a parent-linked chain: each
`Turn` stores the id of its parent, and `Session.history()` walks backward from the head until a
`summary` turn or the root. This makes branching structural rather than a separate table.

- `InMemoryMessageLogStore` is used in tests and ephemeral runs.
- `SQLiteMessageLogStore` (in `agentbox-models`) persists turns as `TurnRow` rows.
- A `summary` turn replaces a prefix of the chain after compaction; later reads start there.
- Forking reuses an earlier turn as the head; retry re-runs from a user turn without appending a
  duplicate user turn.

See the [data model](05-data-model.md) for how the chain is stored and queried.

## Runs and the event bus

`Harness.run` starts an asynchronous run and returns a `Run`. A run owns an `asyncio.Task` and a
`CancellationToken`. `RunManager._drive` calls `agent.run_stream_events(...)`, wraps every
pydantic-ai event as a `RunEvent(run_id, seq, event)`, and publishes it on an `EventBus`.

`EventBus` keeps a replay history and a queue per subscriber. A subscription yields events in
sequence order and ends when the bus closes. If the model raises a context-window error, the run
invokes middleware recovery; when recovery produces new history, the run retries once.

*Figure 1 — Run and event flow.*

```mermaid
sequenceDiagram
  participant H as Harness
  participant S as Session
  participant RM as RunManager
  participant A as pydantic-ai Agent
  participant B as EventBus
  participant Sub as Subscriber

  H->>S: history()
  S-->>H: turns
  H->>RM: start(agent, message history)
  RM->>A: run_stream_events
  loop streaming
    A-->>RM: event
    RM->>B: publish RunEvent(run_id, seq)
    B-->>Sub: replay + live events
  end
  A-->>RM: final result or error
  RM->>B: close()
```

## Harness orchestration

`Harness` wires together the spec, the resolved model, a message-log store, middleware, and the
MCP session manager. Its main methods:

- `start_session(store, head_id)` returns a `Session`.
- `run(...)` resolves the mode, runs `prepare_mcp`, appends the user turn (unless retrying),
  builds the agent, and delegates to the run manager.
- `run_turn(...)` is a blocking convenience wrapper around `run`.
- `prepare_mcp(...)` starts or reuses session-scoped stdio MCP servers and reports warnings.

*Figure 2 — Agent assembly.*

```mermaid
flowchart TB
  spec["AgentSpec"] --> factory["build_agent"]
  factory --> native["Native tools selected by mode"]
  factory --> subagents["Sub-agent tools"]
  factory --> subsessions["Sub-session tools"]
  factory --> remote["Remote MCP toolsets"]
  factory --> stdio["Pre-started stdio MCP toolsets"]
  native --> agent["pydantic-ai Agent"]
  subagents --> agent
  subsessions --> agent
  remote --> agent
  stdio --> agent
```

## Agent assembly and tool selection

`build_agent` is where an agent definition becomes a runnable agent:

1. Resolve the active mode and its flags.
2. Select native tool names from the spec and filter them through the `ToolRegistry`, which
   enforces required flags.
3. Add delegated sub-agent tools when sub-agent ids are present, with a depth cap of 3.
4. Add sub-session tools in write mode.
5. Add remote MCP toolsets (rebuilt per agent build).
6. Attach already-started stdio MCP toolsets from the session-scoped manager.

*Figure 3 — Mode-based tool selection.*

```mermaid
flowchart LR
  mode["Mode"] -->|"write = false"| ask["Ask: read-only tools"]
  mode -->|"write = true"| agent["Agent: read and write, terminal, sub-sessions"]
  registry["ToolRegistry.required_flags"] --> ask
  registry --> agent
```

## Middleware and compaction

`RunMiddleware` receives a `RunContext` and can act before a run and when recovering. The
compaction middleware is the main implementation:

- It estimates tokens with `len(content) / 4`.
- It triggers when the estimate crosses `compaction_ratio * context_window`, or when the model
  reports a context-window overflow.
- It summarizes older turns with a separate `Agent` call, inserts a `summary` turn, and rewires
  the chain so subsequent history starts at the summary.
- It keeps a configurable number of recent turns and caps the summary size.

Compaction can run proactively before a turn or reactively during overflow recovery. After a
successful recovery the run retries once.

## Sub-agents and sub-sessions

The harness supports two delegation models:

- **Sub-agents** are exposed to the model as ordinary tools. Each call runs an isolated agent run
  in-process and returns its output. Depth is capped at 3.
- **Sub-sessions** are background child sessions with their own persisted `SessionRow`, status,
  and output. The model gets `start`, `list`, `get`, and `cancel` tools. The API layer provides a
  `SubSessionRunner` implementation with concurrency and depth caps; see
  [concurrency and lifecycle](10-concurrency-and-lifecycle.md).

## Toolboxes

| Toolbox | Highlights |
|---|---|
| Filesystem | Read, write, edit, copy, move, guarded delete; tree, search, file info; media reads with Pillow downscaling; project root and extra-root path guards |
| Grep | Pure-Python content search with file/line/result/walk limits and excluded directories |
| Terminal | Global `JobManager`, max 20 jobs per session, per-job output drain, truncation, process-tree kill, configurable timeout |
| Web | Keyless search via ddgs/SearXNG; HTTPS fetch with SSRF guards, redirect revalidation, size limits, and HTML-to-Markdown extraction |

Every native tool can have post-result hooks. Two hooks are registered by the API layer: LSP
diagnostics after writes, and nested `AGENTS.md` instruction injection.

## LSP diagnostics

The `LspManager` is a process-global singleton. It detects a project's stacks (Python,
TypeScript, Rust) from marker files, starts one server per `(project_root, stack)`, and caches
failures with a backoff. After a write tool runs, a hook syncs the changed document, waits for
diagnostics to settle, and appends formatted diagnostics to the tool result. Rust uses
server-status notifications to detect quiescence instead of a fixed delay. There is no idle
eviction; servers live until shutdown.

## Implementation notes

> **Implementation note:** when a model override is supplied, `Harness.run` still constructs the
> agent with `self.model`; the override is passed only to `run_stream_events`. Treat the override
> as a run-level argument, not an agent-level one.

> **Implementation note:** the harness is protocol-agnostic by design. ACP, A2A, and AG-UI all
> consume the same `EventBus` and differ only in event mapping and persistence finishing.

## Related

- [Backend](03-backend.md)
- [Data model](05-data-model.md)
- [Protocols](07-protocols.md)
- [Concurrency and lifecycle](10-concurrency-and-lifecycle.md)
- [Index](README.md)
