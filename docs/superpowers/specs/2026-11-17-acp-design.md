# ACP (Agent Client Protocol) Adapter — Design Specification

- **Date:** 2026-11-17
- **Status:** Draft (brainstormed; approved scope; pending implementation plan)
- **Sub-project:** ACP adapter — let an external IDE drive Agentbox sessions over ACP (JSON-RPC over stdio), adapting the core session storage.

## 1. Context and Scope

The initial spec lists **ACP (Agent Client Protocol)** for "communication between the agentic system and an IDE" (`initial_spec.md:9`) and "an external IDE uses the application, probably via an RPC protocol over STDIO. The external IDE starts and manages sessions in the way closest to what could have been managed directly via the application's user interface." (`initial_spec.md:98-100`).

"ACP" here is Zed's **Agent Client Protocol** (`agentclientprotocol.com`); the Python SDK is `agent-client-protocol` (import `acp`), version **1.0.0** (stable v1 protocol; v2 is draft — not used).

### 1.1 What this sub-project encompasses
- An ACP stdio server (`agentbox-acp` / `python -m agentbox_api.acp_server`) implementing the v1 protocol via the official SDK.
- Driving the existing harness (`Session`, `EventBus`, `SQLiteMessageLogStore`) and adapting the core session storage (`Project`, `SessionRow`, `TurnRow`) to ACP `session/*`.
- Prompt content: text, `resource_link`, image, audio, embedded resources.
- Client-provided stdio MCP servers.
- Session lifecycle: new, prompt, cancel, and (backed by core storage) list, load, resume, delete, close.
- Session modes (Ask/Agent).

### 1.2 Boundaries
- No frontend changes (ACP is for external IDEs).
- v1 protocol only (not the v2 draft).
- No HTTP/SSE transports; no client `fs/*`/`terminal/*`; no ACP auth.

### 1.3 Dependencies
- `agentbox-api`; new Python dep `agent-client-protocol>=1.0`.

## 2. Compliance Matrix

**Baseline MUSTs** (must be implemented):
- `initialize` (respond with `protocolVersion` + capabilities + `agentInfo`).
- `session/new`, `session/prompt`, `session/cancel`, `session/update`.
- Prompt content `text` and `resource_link`.
- Client-provided MCP servers over **stdio** ("All Agents MUST support connecting to MCP servers via stdio"; "SHOULD connect to all MCP servers specified by the Client").

**Implemented (optional, advertised)**: `promptCapabilities.image/audio/embeddedContext`; `loadSession`; `sessionCapabilities.list/delete/resume/close`; session modes.

**Omitted (optional, not advertised → clients MUST NOT call/send)** — each justified:

| Omitted | Normative status | Justification |
|---|---|---|
| `additionalDirectories` | clients **MUST only send** if advertised (`sessionCapabilities.additionalDirectories`) | Not advertised; `cwd` is the sole root. |
| `systemPrompt` | clients **MUST only send** if advertised (`sessionCapabilities.systemPrompt`) | Not advertised; agents use their own instructions. |
| `session/request_permission` | **MAY** (`tool-calls.md`) | Optional; write access is governed by session **mode** (Ask disables writes). |
| `fs/*`, `terminal/*` | client capabilities the agent **MAY** use | Tools run server-side against `cwd`; not needed. |
| `notices`, `compaction` | agent **MUST NOT** send unless the client advertises `session.notices`/`session.compaction` | We never emit them. |
| `usage_update`, `plan`, `available_commands_update`, `config_option_update`, `session_info_update` | **MAY**/optional | Not emitted; text/tool updates suffice. |
| `mcpCapabilities.http/.sse` | OPTIONAL (stdio is the MUST) | We support stdio only; not advertised. |
| ACP `auth`/`authMethods` | OPTIONAL | Local stdio process; `authMethods: []`. |

Governing principle (`initialization.md`): capabilities are opt-in; an agent "SHOULD specify whether it supports" the optional ones; both sides "MUST treat all capabilities omitted as UNSUPPORTED".

## 3. Decisions and Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Use the official `agent-client-protocol` SDK (no homegrown JSON-RPC). | Mandatory protocol compliance. |
| D2 | Agent chosen by `--agent <name>` (CLI only); `cwd` = project root. | IDE configures the command; explicit selection. |
| D3 | Adapt core session storage (`Project`/`SessionRow`/`TurnRow`) for ACP sessions. | Reuse the existing persistence and the UI's session model; enables list/load/resume/delete/close. |
| D4 | Implement full ACP session lifecycle, advertised via capabilities. | Data already exists; "closest to the UI". |
| D5 | Support text, `resource_link`, image, audio, embedded content; advertise all. | Baseline MUSTs + richer prompt content. |
| D6 | Support client-provided stdio MCP servers per session. | Baseline MUST (stdio) + SHOULD connect. |
| D7 | Session modes map to the agent's `mode_definitions`. | Matches the in-app Ask/Agent modes. |

## 4. Architecture

- `agentbox_api/acp_server.py`: `AgentboxAcpAgent(acp.Agent)` + `main()` CLI (`--agent`).
- `agentbox_api/runtime.py`: shared helpers `build_registry(project_root)`, `resolve_agent_runtime(factory, agent_name)` (reused by the chat router and the ACP server).
- Harness: `Harness.run` + `EventBus` stream (same as the chat endpoint).

### 4.1 Agent methods
- `initialize(protocol_version, client_capabilities, client_info)` → `protocolVersion=1`, `agentInfo`, `authMethods=[]`, `promptCapabilities={image,audio,embeddedContext: true}`, `loadSession=true`, `sessionCapabilities={list,delete,resume,close}`, no `mcpCapabilities.http/sse`.
- `new_session(cwd, mcp_servers)` → find-or-create a `Project` for `cwd` (name = basename; owner = the agent's `created_by`, else the seeded `admin`), create a `SessionRow` (id = ACP sessionId, agent_id = configured agent), build a harness `Session` with `SQLiteMessageLogStore`, merge the stdio `mcpServers`, store `AcpSession` in memory; return `sessionId` + `modes`.
- `list_sessions(cwd?)` → query `SessionRow` joined to `Project` where `project.path == cwd` (if given) and `agent_id == configured agent`; `SessionInfo {sessionId, cwd: project.path, title (first user turn, truncated), updatedAt (latest turn)}`.
- `load_session(session_id, cwd, mcp_servers)` → restore the harness session, **replay** persisted turns as `user_message_chunk`/`agent_message_chunk` updates, respond.
- `resume_session(session_id, cwd, mcp_servers)` → restore the harness session (`head_id` = latest leaf) **without replay**, respond.
- `delete_session(session_id)` → delete the `SessionRow`, its turns, and attachments; respond `{}`.
- `close_session(session_id)` → cancel any active run, drop the in-memory session (keep DB rows); respond `{}`.
- `prompt(session_id, prompt)` → convert blocks; run the harness; stream updates; respond with a stop reason.
- `cancel(session_id)` → `run.cancel()`.
- `set_session_mode(session_id, mode_id)` → update the session's mode.

### 4.2 Content conversion (`prompt_override` list)
- `text` → `str`.
- `resource_link` → `"[resource: <name> <uri> (<mimeType>)]"`.
- `image`/`audio` → `BinaryContent(base64decode(data), mimeType)`.
- `resource` text → a text part labeled with `uri`/`mimeType`; `resource` blob → `BinaryContent(base64decode(blob), mimeType)` + a text label.
- Unknown block → JSON-RPC `invalid_params` error (never silently dropped).

### 4.3 Streaming mapping (pydantic-ai stream events → ACP `session/update`)
- text delta → `agent_message_chunk` (`text_block`).
- thinking delta → `agent_thought_chunk` (`text_block`).
- `FunctionToolCallEvent` → `tool_call` (id, title=name, name, kind="other", status="pending").
- `FunctionToolResultEvent` → `tool_call_update` (status `completed`/`failed`, content `tool_content(text_block(...))`).
Use `acp.helpers`; send via the ACP connection's `session_update`.
- Completion: harness `outcome.status` success → `end_turn`; cancelled → `cancelled`; error → send the error text as an `agent_message_chunk` then `end_turn`.

### 4.4 Stdio MCP servers
- Extend `McpToolBinding` with `command: str = ""`, `args: list[str] = []`, `env: dict[str, str] = {}` (URL binding stays for HTTP).
- `build_mcp_toolset` builds a stdio `MCPToolset` when `command` is set, else a URL `MCPToolset`.
- On `new_session`/`load`/`resume`, each ACP stdio `mcpServers` entry becomes an extra `McpToolBinding` appended to a per-session copy of the agent spec.

### 4.5 Entry point
`agentbox-acp` console script (`[project.scripts]`) and `python -m agentbox_api.acp_server`, taking `--agent <name>`; `DATABASE_URL`/`Settings` selects the DB; `run_agent(agent)` runs the stdio loop.

## 5. Testing

- **Unit (`tests/test_acp.py`)**:
  - Content conversion for text/link/image/audio/embedded → prompt parts.
  - Session lifecycle with a seeded DB: `new_session` (creates Project+Session), `list_sessions` (title/cwd), `load_session` replay, `resume_session`, `delete_session` (row + turns gone), `close_session`.
  - Modes: `new_session` returns the agent's modes; `set_session_mode`.
- **Real stdio E2E (`tests/test_acp_stdio.py`)**: spawn the server as a subprocess (`acp.spawn_agent_process`) with a seeded temp SQLite DB and a `test`-provider agent; `initialize` → `new_session(cwd)` → `prompt([text_block])`; assert an `agent_message_chunk` contains the test provider text and `stop_reason == end_turn`; then `session/list` returns the session and `session/load` replays history.

## 6. Error Handling

- Unknown content block → `invalid_params`.
- Unknown session id / wrong agent → `unknown session` error.
- Harness error → error text + `end_turn`.
- Cancellation → `cancelled` stop reason (never an error response).
- Never log MCP `env`/`headers` values (security).

## 7. Open Items / Future Work

- HTTP/SSE client MCP transports (`mcpCapabilities`).
- `request_permission` prompts; `fs/*`/`terminal/*` client capabilities; `additionalDirectories`; `systemPrompt`.
- `plan`, `usage_update`, `slash commands`, `configOptions`, `notices`, `compaction`.
- v2 protocol (draft).

## References

- Initial spec — `docs/initial_spec.md:9, 98-100`.
- ACP v1 docs — `https://agentclientprotocol.com/protocol/v1/`; Python SDK — `https://github.com/agentclientprotocol/python-sdk`.
- Existing session code — `packages/agentbox-models/src/agentbox_models/tables/core.py` (`Project`, `SessionRow`, `TurnRow`), `repos/message_log.py`, `routers/sessions.py`; harness `Session`, `EventBus`, `Run`.
