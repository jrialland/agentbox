# ACP Client Capabilities - Design

Date: 2026-11-22
Status: Approved (design); spec awaiting review.

## Goal

Implement the complete ACP v1 client capability surface in the Agentbox ACP adapter:
`fs/read_text_file`, `fs/write_text_file`, and every `terminal/*` method. Use the client
when it advertises the capability, otherwise keep the existing server-side tools.

This is full ACP compliance. It is not an attempt to invent ACP methods for Agentbox
filesystem operations that ACP does not define.

## The ACP v1 client surface

The installed `agent-client-protocol` SDK exposes exactly these client operations:

- `fs/read_text_file`: `read_text_file(session_id, path, line=None, limit=None)`.
- `fs/write_text_file`: `write_text_file(session_id, path, content)`.
- `terminal/create`: `create_terminal(session_id, command, args=None, env=None, cwd=None,
  output_byte_limit=None)`.
- `terminal/output`: `terminal_output(session_id, terminal_id)`.
- `terminal/wait_for_exit`: `wait_for_terminal_exit(session_id, terminal_id)`.
- `terminal/kill`: `kill_terminal(session_id, terminal_id)`.
- `terminal/release`: `release_terminal(session_id, terminal_id)`.

`ClientCapabilities.fs` has `read_text_file` and `write_text_file` booleans.
`ClientCapabilities.terminal` is a single boolean that covers all `terminal/*` methods.

ACP v1 has no client methods for media/binary files, directory listing, mkdir, move,
delete, copy, or stat. Those remain Agentbox server-side tools. Keeping them server-side is
not an ACP compliance gap.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Install ACP tool overrides on the existing `ToolRegistry` from the ACP adapter. | Keeps the harness protocol-agnostic; no ACP imports in the harness. |
| D2 | Implement every ACP-defined client method. | Full ACP compliance, not a subset. |
| D3 | Compose Agentbox tools from ACP primitives where ACP has the primitives: `edit_file`, `append_file`, `copy_file`, `read_file`, and `read_multiple_files`. | These operations are expressible through ACP read/write and should use the IDE. |
| D4 | Keep non-ACP filesystem tools server-side: media, directory/tree/search/grep/info, mkdir, move, delete. | ACP defines no methods for them; terminal-based or fake implementations would be misleading. |
| D5 | Route only paths inside the project root plus extra roots to ACP. Fall back to the original tool for other paths. | Skills and other read roots may be outside the ACP workspace; the IDE may reject them. |
| D6 | Override only tools already bound by the agent. | Preserves the agent's tool configuration and Ask/Agent mode gating. |
| D7 | Surface ACP client errors for routed paths. Do not silently retry them server-side. | Hiding client failures would make the IDE behavior unpredictable. |
| D8 | Track ACP terminals per ACP session and release them on close/delete. | Mirrors the existing `JobManager` lifecycle and avoids leaked client terminals. |
| D9 | Keep the existing server-side tools when a capability is absent. | ACP clients may advertise no fs or terminal support. |

## Architecture

### ACP adapter

Add `agentbox_api/acp_client_tools.py`:

- `AcpClientTools` - per-session state: `client`, `session_id`, `project_root`,
  `extra_roots`, `capabilities`, and the terminal tracker.
- `AcpClientCapabilities` - `read_text_file`, `write_text_file`, `terminal`. Build it from
  `s.ClientCapabilities`, treating missing/None as false.
- `install_acp_client_tools(registry, spec, state)` - capture the raw original tools and
  replace the supported ones through `registry.override_native(...)`.
- `AcpClientTools.close()` - kill/release tracked terminals.
- `AcpTerminalTracker` - background terminal jobs keyed by ACP terminal id.

The adapter stores the capabilities captured by `initialize` and installs the tools in
`new_session` and `_restore`. `AcpSession` gains a `client_tools` field. `close_session`
and `delete_session` release the session's ACP terminals before removing the session.

If a session is loaded/resumed over an existing in-memory session, close the old
`client_tools` first.

### Registry support

`ToolRegistry` gains:

- `get_native_raw(name)` - the original callable before hook wrapping.
- `override_native(name, callable)` - replace a tool while preserving its
  `required_flags` and applying hooks once.

This avoids double-running hooks when an ACP wrapper falls back to server-side behavior.

### Harness helpers

Expose two existing private helpers for the adapter:

- `agentbox_harness.tools.filesystem.apply_file_edit(text, edit, newline)` - used by
  `edit_file` both server-side and through ACP.
- `agentbox_harness.tools.terminal.shell_command(command)` - the existing shell wrapper
  used to turn a command string into executable plus arguments for `create_terminal`.

No ACP-specific code enters the harness.

## Filesystem routing

| Agentbox tool | ACP path | Requirements |
|---|---|---|
| `read_text_file` | ACP read full content, then apply `head`/`tail` locally. | `readTextFile` |
| `read_file` | ACP read full content. | `readTextFile` |
| `read_multiple_files` | ACP read each path; if any path is outside allowed roots, fallback to the original tool for the whole call. | `readTextFile` |
| `write_file` | ACP write. | `writeTextFile` |
| `append_file` | ACP read existing content (missing file means empty), append, ACP write. | read + write |
| `edit_file` | ACP read, apply `apply_file_edit`, ACP write; `dry_run` returns the diff without writing. | read + write |
| `copy_file` | ACP read source, ACP write destination. | read + write |
| `read_media_file` | Server-side. | No ACP method |
| `list_directory`, `list_directory_with_sizes`, `directory_tree` | Server-side. | No ACP method |
| `search_files`, `grep`, `get_file_info`, `list_allowed_directories` | Server-side. | No ACP method |
| `create_directory`, `move_file`, `delete_path` | Server-side. | No ACP method |

Preserve the current return messages and validation behavior:

- errors for head+tail together, non-regular files, missing parent directories, existing
  copy destinations, and path escapes;
- `Wrote N bytes to path`, `Appended N bytes to path`, `Edited path`,
  `Copied source to destination`, and the existing `read_multiple_files` framing.

Path routing uses `resolve_project_path(path, project_root, extra_roots)`. If the path is
outside those roots, the wrapper calls the captured raw original tool. This lets skill files
and other read-only roots continue to work server-side.

## Terminal routing

When `terminal` is true and the agent binds terminal tools, replace all four:

### `run_command(command, cwd=None, timeout=30, background=False)`

- Resolve `cwd` with `resolve_project_path`; a path escape returns
  `Command failed: ...` as today.
- Build executable and args with `shell_command(command)`.
- Call `create_terminal(session_id, command=exe, args=args, cwd=str(cwd),
  output_byte_limit=200000)`.
- Track the terminal in the per-session tracker.

Foreground:

- `await asyncio.wait_for(wait_for_terminal_exit(...), timeout)`.
- On timeout, `kill_terminal`, mark timed out, then read output and release.
- Otherwise read `terminal_output`; release the terminal.
- Return the existing status/duration/truncation/output shape.

Background:

- Return `Started job <terminal_id>: <command>` and the `get_job_output` hint.
- Keep the terminal tracked until killed, released, or session close.

### `list_jobs()`

Refresh each tracked job through `terminal_output`, derive
`running|completed|failed|killed`, include exit/signal, age, and a capped command summary.
Most recent first.

### `get_job_output(job_id, max_chars=10000)`

Call `terminal_output`, include status/exit and truncated marker, and cap the returned text.
Clamp `max_chars` to 100..100000.

### `kill_job(job_id)`

Call `kill_terminal`, then `release_terminal`, mark killed, and report if already finished.

### Session close/delete

Kill running terminals and release every tracked terminal. Suppress client errors so cleanup
is idempotent.

## Error handling

- Capability absent: do not install the wrapper; the server-side tool remains.
- Tool not bound by the spec: do not install the wrapper.
- Path outside project/extra roots: call the raw server-side tool.
- ACP request failure for a routed path: propagate the error through the tool guard; do not
  retry server-side.
- Client disconnect during a run: the existing ACP run error handling applies; terminal
  cleanup is best-effort.
- Invalid `head`/`tail`, missing files, and parent-directory checks keep their existing
  error semantics.

## Testing

- `packages/agentbox-api/tests/test_acp_client_tools.py` with a fake `acp.Client`:
  - capabilities absent -> no overrides;
  - read/write only -> only the corresponding tools are overridden;
  - read/write edit, append, copy, and read-multiple behavior;
  - outside-root fallback calls the raw tool;
  - ACP errors are surfaced for routed paths;
  - terminal foreground success, timeout, background start, list, output, kill, and close;
  - no terminal capability -> no terminal overrides.
- `packages/agentbox-harness/tests/test_tool_registry.py`: raw access and override preserve
  required flags and run hooks once.
- `packages/agentbox-api/tests/test_acp.py`: capability installation and session lifecycle
  with a fake client.
- `packages/agentbox-api/tests/test_acp_stdio.py`: initialize with client `fs` and
  `terminal` capabilities and run an agent that calls `read_text_file`; assert the client
  received the ACP read. Add a terminal call test if the test provider can be extended
  cheaply.
- Existing server-side filesystem/terminal tests must continue to pass when capabilities
  are absent.

## Out of scope

- ACP media/binary, directory listing, mkdir, move, delete, and stat: ACP defines no client
  methods for them, so they remain server-side. `copy_file` is the exception: it is composed
  from ACP read/write, not an ACP copy method.
- Client `request_permission`, ACP auth, and new UI surfaces.
- Remote/SSH ACP clients; this design assumes the existing local stdio process.
- Changing agent tool bindings or mode gating.

## Risks

- ACP clients vary in their filesystem/terminal implementations; client errors are surfaced
  rather than masked.
- Terminal shell wrapping differs by OS; it reuses the existing `shell_command` behavior.
- Paths outside the project/extra roots bypass the IDE and use server-side tools; this is
  intentional so skills and global roots keep working.
- ACP client calls add latency compared with direct local file access.
- Releasing terminals is best-effort; a dead client may leave its own process cleanup to the
  client.

## References

- ACP v1 client protocol - `agentclientprotocol.com`; Python SDK `agent-client-protocol`.
- Existing adapter - `packages/agentbox-api/src/agentbox_api/acp_server.py`.
- Existing tools - `packages/agentbox-harness/src/agentbox_harness/tools/filesystem.py`,
  `packages/agentbox-harness/src/agentbox_harness/tools/terminal.py`.
- Roadmap - `docs/ROADMAP.md` D23.
