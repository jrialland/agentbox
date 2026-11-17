# Agentic Harness — Design Specification

- **Date:** 2026-11-17
- **Status:** Draft (brainstormed, pending implementation plan)
- **Sub-project:** Agentic harness (runtime + tool system + sessions)

## 1. Context and Scope

This specification covers the **agentic harness** sub-project of the Agentbox platform — the runtime that executes agents, manages their tools, and runs sessions. It is one of several sub-projects decomposed from the initial platform specification (`docs/initial_spec.md`).

### 1.1 What the harness encompasses

- **Runtime** — how an agent (system prompt + tools + model + mode) executes a session, including the tool loop, sub-agent spawning, and streaming.
- **Tool system** — built-in file tools, MCP-backed tools, tool registration/discovery, and capability-flag-based modes.
- **Sessions** — conversation history, resume, question editing (branching), and run lifecycle.

### 1.2 Boundaries (out of scope for this sub-project)

- **SQLite persistence** — the harness consumes *resolved* objects; storage is defined in the data-model sub-project.
- **LLM provider implementation** — the harness consumes a `ModelBinding` interface (provider + model name); the provider layer is a separate sub-project.
- **RBAC / authentication** — separate sub-project.
- **HTTP / protocol layers** — the backend API (FastAPI) and the ACP/A2A protocol adapters are separate sub-projects. Only the canonical event stream and the built-in AG-UI adapter fall within this scope (see §5).

### 1.3 Dependencies

- Data model + persistence (resolved `AgentSpec`, message log store).
- LLM provider layer (the `ModelBinding` interface).
- Core `pydantic-ai` (no `pydantic-ai-harness`).

## 2. Decisions and Rationale

The following decisions were reached during brainstorming and are documented to make the reasoning recoverable.

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Build on **core `pydantic-ai` only** (no `pydantic-ai-harness` package). | Full control over file-tool semantics, sub-agent spawning, persistence, and modes; exact parity with MCP FileSystem behavior; minimal dependency surface. Core pydantic-ai still provides the agent loop, `Agent` delegation, streaming events, `CancellationToken`, message-history resume, `MCPToolset`, and the built-in `AGUIAdapter`. |
| D2 | **Canonical Pydantic AI event stream + per-protocol adapters.** | ACP (`session/update`) and A2A (`SendStreamingMessage`) have their own wire formats that are lossy to translate from AG-UI. The harness emits one canonical stream; AG-UI uses the built-in `AGUIAdapter`, and ACP/A2A adapters are separate sub-projects. |
| D3 | Sub-agents modeled as **agents-as-tools (isolated sessions)** via core pydantic-ai agent delegation. | Each sub-agent runs in its own isolated run with its own message history, matching the "isolated sessions" requirement. |
| D4 | Modes modeled as **capability flags**. | Tools declare the flags they require; a mode is a named preset of flags applied as run-time tool filtering. |
| D5 | History is an **immutable log + branching**. | Editing a question forks a new branch rather than destructively truncating history. |
| D6 | Filesystem is **sandboxed to the project root**. | File tools cannot escape the session's project root; sensitive paths are guarded by read-only patterns. |
| D7 | Run control is **cancel + detach/re-attach**. | A run is a background task whose event stream is fanned out via a bus; closing the UI detaches the run (it may continue), superseding the initial spec's "closing the browser ends the session." |
| D8 | **Skills are deferred** entirely; noted only as a future integration point. | The initial spec explicitly defers skills. |

## 3. Core Concepts

### 3.1 `AgentSpec`

An immutable, fully-resolved description of an agent. The harness receives resolved `AgentSpec`s and never loads from SQLite directly.

Fields:

- `name` — unique name.
- `description` — short intent/capability description.
- `instructions` — the system prompt.
- `tool_bindings` — which tools the agent may use (native tools + MCP tool references).
- `sub_agent_ids` — which agents it may spawn as sub-agents (may be empty).
- `mode_definitions` — named presets of capability flags (e.g. `ask`, `agent`).
- `model_binding` — reference to the LLM provider + model name.

`AgentSpec` is a plain Pydantic model, serialized to JSON for storage and reconstructed via `Agent.from_spec(...)` or by constructing an `Agent(...)` with the resolved fields. Untrusted specs are validated and audited (capabilities, tools, model references) before construction.

### 3.2 `Tool`

A unified tool abstraction with two implementations, both of which become pydantic-ai `Tool`s so the tool loop, schema extraction, and streaming are identical:

- **`NativeTool`** — a Python function (file tools and other built-ins).
- **`MCPTool`** — a tool wrapped from an MCP server via `MCPToolset` / the `MCP` capability; MCP server tools become agent tools automatically.

Every tool declares `required_flags` (see §4.2).

### 3.3 `Session`

A conversation bound to:

- a **project root** (filesystem sandbox root), and
- an **agent** (`AgentSpec`).

A session holds an **immutable message/turn log** and a **current branch pointer** (see §6).

### 3.4 `Run`

One execution of the agent over a session (a single "send message → … → finish" cycle). Runs are first-class with their own lifecycle (§6.3). One session can have many runs over time.

### 3.5 `Mode`

A named preset of capability flags. Examples from the initial spec:

- `ask` — `{ write: false }` (filesystem write tools disabled).
- `agent` — `{ write: true }` (full tool set).

Modes are defined per agent in the agent configuration interface and applied at run start.

## 4. Tool System

### 4.1 Native file tools

Native file tools mirror the **MCP FileSystem** reference server's semantics and names, and are sandboxed to the session's project root:

- `read_text_file`, `read_multiple_files`, `list_directory`, `search_files`, `get_file_info`, `directory_tree`
- `write_file`, `append_file`, `edit_file`, `create_directory`, `move_file`, `copy_file`

Behavior:

- All paths resolve against the project root; escaping the root is rejected.
- Read-only patterns guard sensitive paths (e.g. `.git`, `.env`, secrets).
- `edit_file` takes an `edits` array of `oldText`/`newText` (mirroring MCP FileSystem), with a `dryRun` option.

### 4.2 Modes (capability flags)

- Each tool declares `required_flags` (e.g. a `write_file` tool declares `write`).
- A `Mode` is a named mapping `{ flag: bool }`.
- At run start, the `RunManager` computes the active mode's flags and registers only the tools whose `required_flags` are satisfied.

### 4.3 MCP tools

MCP tools are brought in via `MCPToolset` / the `MCP` capability, referencing an MCP server by URL or stdio transport. MCP server tools become agent tools automatically, sharing the same `Tool` abstraction as native tools.

MCP **Apps** (interactive UIs served by MCP servers via `ui://` resources) are surfaced through the frontend as left-hand tabs (a separate frontend concern); the harness only needs to expose the app resource/tool entry points (e.g. `read_resource_for_app` / `call_tool_for_app`) for the backend/frontend to consume.

## 5. Run Execution and Streaming

### 5.1 Canonical event stream

The `RunManager` drives execution using `agent.run_stream_events()` (or `agent.iter()` for finer node-level control), producing a canonical Pydantic AI event stream:

- `PartStartEvent` / `PartDeltaEvent` (text and tool-arg deltas)
- `ThinkingPartDelta` (reasoning deltas)
- `FunctionToolCallEvent` / `FunctionToolResultEvent`
- `CustomEvent` (application-defined progress/status)
- `FinalResultEvent` / `AgentRunResultEvent`

### 5.2 Protocol adapters

The canonical stream is consumed by protocol adapters:

- **AG-UI** — the built-in `AGUIAdapter` (`pydantic_ai.ui.ag_ui`) converts the stream to AG-UI SSE events (`RUN_STARTED`, `TEXT_MESSAGE_*`, `TOOL_CALL_*`, `REASONING_*`, `CUSTOM`, `RUN_FINISHED`, `RUN_ERROR`), including tool calls, reasoning, custom events, interrupts/tool approval, and cancellation.
- **ACP** and **A2A** — separate sub-projects; each implements its own adapter over the canonical stream.

Reasoning is surfaced as reasoning/thinking parts. Markdown and Mermaid rendering are frontend concerns; the harness only emits the text deltas.

## 6. Sessions, History, and Run Lifecycle

### 6.1 Immutable log + branching

- Conversation history is an **immutable message log** persisted in SQLite, keyed by session and turn.
- A session's current position is a **branch pointer** into the log.
- **Editing a question** forks a new branch (new head pointer) without deleting prior history.

### 6.2 Resume

Resuming a session reconstructs `message_history` from the persisted log and passes it to the next run via `agent.run(message_history=...)`.

### 6.3 Detach/re-attach and cancellation

- A `Run` executes as a background `asyncio` task.
- Its event stream is fanned out to subscribers through an **event bus**.
- **Detach** unsubscribes a UI consumer while the run continues; **re-attach** replays missed events (snapshot + subsequent deltas) and re-subscribes.
- **Cancellation** uses a per-run `CancellationToken`; on cancel, `RunCancelled.all_messages()` yields the resumable history, which is persisted.

## 7. Sub-Agents

Implemented via core pydantic-ai **agent delegation**:

- Each `sub_agent_id` maps to a native tool that calls `sub_agent.run(task, ...)` in its own **isolated run** (fresh message history, its own usage accounting).
- The parent agent lists which sub-agents it may spawn (`sub_agent_ids`).
- Recursion depth and usage limits are bounded to prevent runaway delegation.

## 8. Error Handling

The following are normalized to typed outcomes and surfaced as canonical events (so AG-UI emits `RUN_ERROR`/`RUN_FINISHED` correctly, and ACP/A2A map them):

- Tool execution errors.
- `UsageLimitExceeded`.
- `RunCancelled` (reported as a cancelled finish, never as an error).
- Model/provider errors.

## 9. Testing

- Unit-test each native file tool, including the **sandbox boundary** (escaping the root is rejected).
- Unit-test mode-filtering logic (correct tools enabled per flag preset).
- Unit-test branching and resume logic.
- Test the `RunManager` using pydantic-ai's `TestModel` / `FunctionModel` — no real LLM calls required.
- Protocol adapters are tested with recorded/representative event sequences.

## 10. Open Items / Future Work

- **Skills** — deferred; future integration point is a skill registry that the harness can expose to the model as context/tools.
- **ACP and A2A adapters** — separate sub-projects, each with their own spec.
- **MCP Apps rendering** — frontend concern (left-hand tabs), pending the frontend sub-project spec.

## References

- Pydantic AI docs — Agents, Tools, Streaming, Multi-agent, MCP client/server, AG-UI integration (`pydantic.dev`).
- AG-UI protocol — `docs.ag-ui.com`, `github.com/ag-ui-protocol/ag-ui` (v1.0, 31 event types across 8 families).
- Agent Client Protocol (ACP) — `agentclientprotocol.com`, `github.com/agentclientprotocol/agent-client-protocol`.
- A2A — `a2a-protocol.org`, `github.com/a2aproject/A2A`.
- MCP — `modelcontextprotocol.io`; MCP Apps — SEP-1865 (`github.com/modelcontextprotocol/ext-apps`); MCP FileSystem server — `github.com/modelcontextprotocol/servers`.
