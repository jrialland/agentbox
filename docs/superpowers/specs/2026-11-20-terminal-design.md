# Terminal Session Management + Project Allowed Roots - Design

Date: 2026-11-20
Status: Approved (design), spec awaiting review.

## Goal

Give agents an opt-in terminal capability: run foreground commands, start
background jobs, read job output, and kill jobs. Add per-project allowed roots
so file tools and terminal commands can target explicitly authorized folders
outside the project directory.

## Decisions

- **Four terminal tools**: `run_command` (with `background` flag), `list_jobs`,
  `get_job_output`, `kill_job`.
- **Auto shell per OS**: PowerShell on Windows, bash (fallback `/bin/sh`) on
  POSIX.
- **Session-scoped in-memory jobs**; no persistence across backend restarts.
- **Write-flag gated** and selectable per agent; Ask mode disables terminal.
- **Project extra roots are read + write** for file tools and may be used as
  terminal `cwd`.
- **No terminal UI** in v1; commands and results flow through normal tool-call
  events. A project settings modal edits allowed roots.

## Project allowed roots

### Data model

`Project` gains:

```python
extra_roots: list[str] = Field(
    default_factory=list,
    sa_column=Column(JSON, nullable=False, server_default="[]"),
)
```

Alembic revision `project_extra_roots` (down_revision `e1f2a3b4c5d6`) adds the
`extra_roots` JSON column to `project` with server default `[]`.

Paths are stored as entered. At runtime each path is expanded (`~`), resolved
against the project root when relative, and normalized. Empty entries are
ignored.

### API

- `ProjectCreate.extra_roots: list[str] = []`.
- `ProjectUpdate.name: str | None`, `ProjectUpdate.extra_roots: list[str] | None`.
- `PUT /projects/{pid}` updates name and/or extra roots, returns the project,
  and requires `projects:create` (no separate update permission exists).
- `POST /projects` and `GET /projects` include `extra_roots` as a list via the
  SQLModel JSON column.

### UI

- New Project modal gains an “Additional allowed folders” textarea, one path
  per line.
- A project settings modal, opened from the project tree, edits name and extra
  roots for an existing project.
- Empty lines are dropped; values are sent as a string array.

### Wiring

`prepare_agent(..., extra_roots: list[str] | None = None)` resolves the list and
passes it to:

- `build_registry(..., extra_write_roots=resolved)` → `FilesystemToolbox`;
- `make_terminal_tools(..., allowed_roots=[project_root, *resolved])`.

`FilesystemToolbox` gains `extra_write_roots`:

- write roots = project root + extra write roots;
- read roots = project root + extra write roots + skill dirs;
- write/edit/create/move/copy/delete operations use the write roots;
- `list_allowed_directories` reports the read roots;
- deleting an allowed root itself is still refused.

Chat, ACP, and A2A pass `project.extra_roots` through `prepare_agent`.

## Execution model

- Windows: `pwsh` if available, else `powershell`, invoked with
  `-NoProfile -Command <command>`.
- POSIX: `bash` if available, else `/bin/sh`, invoked with `-c <command>`.
- `cwd` defaults to the project root. Absolute or relative paths are resolved;
  the result must equal or be inside one of the allowed roots.
- Environment is inherited. No per-command env overrides in v1.
- Each command runs in a new process group/session. Timeouts and kills target
  the whole tree (`taskkill /T /F` on Windows, `killpg` on POSIX).
- Output is merged stdout/stderr and decoded as UTF-8 with replacement.

## Terminal tools

| Tool | Semantics |
|---|---|
| `run_command(command, cwd=None, timeout=30, background=False)` | Foreground: wait up to `timeout` (1–300 s), return exit code, duration, and capped output (20 000 chars). `background=True`: start a job, return id/pid, ignore `timeout`. |
| `list_jobs()` | Most-recent-first table of id, status, pid, exit code, age, and command. |
| `get_job_output(job_id, max_chars=10000)` | Tail snapshot of the job's output plus status/exit code. `max_chars` capped at 100 000. |
| `kill_job(job_id)` | Terminate a running job's process tree; report if it already finished. |

Foreground jobs are transient: they are returned inline and removed from the
job list. Background jobs remain listed until the session ends.

## Job manager

`agentbox_harness.tools.terminal`:

- `TERMINAL_TOOL_NAMES = ("run_command", "list_jobs", "get_job_output", "kill_job")`.
- `JobManager` owns processes keyed by session id.
- Statuses: `running`, `completed`, `failed`, `killed`.
- Per-job rolling output tail: 200 000 bytes, with a truncated marker.
- Maximum 20 jobs per session; starting another returns a clear error.
- `kill_session(session_id)` kills running jobs and clears the session.
- `shutdown()` kills every job (called from the API lifespan).
- `get_job_manager()` is a module-level singleton; tests construct a fresh
  `JobManager` and inject it.
- Job ids are 8-character hex strings unique within the session.

Lifecycle:

- `delete_session_data` kills the session's jobs (chat delete, ACP delete).
- ACP `close_session` kills the session's jobs.
- API shutdown kills every job.
- Jobs do not survive a backend restart.

## Wiring and gating

`prepare_agent`, when `session_id` is present and the agent binds any terminal
tool:

- obtains `get_job_manager()`;
- registers all four tools with `required_flags=("write",)`;
- appends missing `NativeToolBinding`s so the four-tool bundle is complete.

Frontend:

- `NATIVE_TOOLS` exposes a single `terminal` checkbox.
- Creating an agent expands `terminal` to the four tool bindings.
- No jobs panel; no terminal emulator.

Ask mode excludes terminal tools through the `write` flag. Agent mode enables
them. Terminal remains opt-in per agent.

## Tests

- Model/API: migration/model roundtrip; create project with extra roots; update
  name/extra roots; list/get return a list.
- Filesystem: read/write/edit/delete under an extra root; denial outside all
  roots; `list_allowed_directories` includes extras; deleting an extra root is
  refused.
- Terminal: shell selection; cwd containment; foreground success and exit
  code; timeout kill; background start/list/output/kill; output truncation;
  job cap; session cleanup and shutdown.
- API wiring: terminal bindings register all four tools with the write flag;
  bundle completion; Ask-mode exclusion; `prepare_agent` passes extra roots.
- Frontend: project create/settings modal; `terminal` expands to four bindings;
  existing tool-picker tests updated.
- No E2E; no terminal UI.

## Out of scope

- PTY/xterm, stdin interaction, interactive programs.
- Job persistence, reconnection, or output history beyond the rolling tail.
- Sandboxing or privilege isolation (see D15).
- Command approvals, allow/deny lists, or per-command environment overrides.
- Explicit shell selection per command.
- Arbitrary `cwd` outside the project root and extra roots.
- Read-only extra roots (authorized roots are read + write).

## Risks

- Commands run with the backend user's privileges; there is no sandbox.
- Allowed roots are a convenience and default-`cwd` boundary, not a shell
  confinement mechanism. A shell can still `cd` elsewhere.
- Windows PowerShell encoding and process-tree behavior differ from POSIX;
  tests use portable commands.
- In-memory jobs are lost on restart.
- Extra roots deliberately expand the file-tool write surface per project.
