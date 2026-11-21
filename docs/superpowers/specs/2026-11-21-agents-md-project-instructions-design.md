# D20 - AGENTS.md Project Instructions

- **Date:** 2026-11-21
- **Status:** Draft (design approved; pending spec review)
- **Sub-project:** D20 - load global and project AGENTS.md guidance into agent and subagent system prompts, with standards-conformant nested discovery and live refresh.
- **Source:** [`AGENTS.md`](https://agents.md/), OpenCode instruction rules, Codex AGENTS.md discovery docs, and the D20 entry in [`docs/ROADMAP.md`](../../ROADMAP.md).
- **Roadmap:** `D20` in [`docs/ROADMAP.md`](../../ROADMAP.md).

## 1. Context and scope

Agentbox agents currently use only the instructions stored on the agent definition, plus prompt templating and the skill catalog. They do not read the repository's AGENTS.md guidance, so project-specific build commands, conventions, and constraints are invisible to the agent.

D20 adds standard AGENTS.md guidance:

- a global `~/AGENTS.md` baseline;
- the project root `AGENTS.md`;
- nested `AGENTS.md` files discovered from directories the agent touches;
- refresh behavior across turns;
- the same guidance for subagents.

### 1.1 In scope

- Load `~/AGENTS.md` as the lowest-precedence global baseline.
- Load `<project_root>/AGENTS.md` as project-wide guidance.
- Discover nested `AGENTS.md` files from the target path of filesystem tools.
- Inject global and root guidance into the system prompt; inject nested guidance into tool results in nearest-last order.
- Refresh root and global guidance on every user run.
- Refresh nested guidance when the relevant path is touched again.
- Preserve last-known content on temporary read failures; clear instructions on file removal.
- Apply a shared 32 KiB instruction budget per session with root -> nested -> global priority.
- Include global and root guidance for background sub-sessions and in-process subagents.
- Structured log events for load, change, removal, truncation, and failure.
- Unit and integration coverage.

### 1.2 Out of scope

- `CLAUDE.md` fallback.
- `AGENTS.override.md`, custom filenames, or configurable global paths.
- AGENTS.md files above the project root other than `~/AGENTS.md`.
- File watchers or mid-run mutation of an already-sent system prompt.
- UI indicators or session-detail metadata.
- Semantic conflict resolution or merging of contradictory instructions.
- AGENTS.md discovery under extra roots or skill directories.
- A screenshot pack; this is a backend/runtime evolution.

### 1.3 Dependencies

- `prepare_agent` in `agentbox_api.skills`.
- `ToolRegistry` and tool hooks in `agentbox_harness`.
- Chat, ACP, A2A, and background sub-session preparation paths.
- Existing loguru logging and session deletion flow.

## 2. Goals and success criteria

- A project can put build, test, style, and safety guidance in AGENTS.md and have every agent follow it.
- Nested guidance is delivered when the agent explores the relevant directory, with the nearest file taking precedence.
- Changes to global or root guidance appear on the next user turn without restarting the session.
- Removing guidance stops it from applying; a transient read failure does not silently discard known guidance.
- Subagents receive the same global, root, and relevant nested guidance.
- Prompt size remains bounded and predictable.
- No UI work is required.

## 3. Decisions and rationale

| # | Decision | Rationale |
|---|---|---|
| D1 | **Global `~/AGENTS.md` + project root + nested files.** | Adds a user baseline while preserving the standard project hierarchy. |
| D2 | **Root and global guidance in the system prompt; nested guidance in tool results.** | Root/global are session-wide; nested guidance belongs to the directory the agent touches. |
| D3 | **Nearest nested file is last and highest precedence.** | Matches AGENTS.md monorepo guidance. |
| D4 | **Shared 32 KiB session budget with root -> nested -> global priority.** | Keeps project-specific guidance ahead of the global baseline without unbounded prompts. |
| D5 | **Refresh root/global every user run; nested on next path touch.** | Matches reference behavior without a watcher or mutating an in-flight prompt. |
| D6 | **Removal clears; read failure preserves last known.** | Avoids stale guidance after deletion without losing guidance on transient I/O errors. |
| D7 | **Logs only, no UI.** | Keeps the evolution runtime-focused and avoids new API/UI surface. |
| D8 | **Reject symlink escapes.** | AGENTS.md must not become an arbitrary file-read path. |
| D9 | **String-returning filesystem tools only for nested injection.** | Avoids changing structured tool return types. |

## 4. Discovery and precedence

### 4.1 Sources

- Global: `Path.home() / "AGENTS.md"`.
- Project root: `<project_root>/AGENTS.md`.
- Nested: `AGENTS.md` in directories between the touched target and the project root, excluding the project root itself.

The global file is resolved by the Agentbox server process's home directory, not the project owner's home.

### 4.2 Precedence

Lowest to highest:

1. global `~/AGENTS.md`
2. project root `AGENTS.md`
3. nested `AGENTS.md`, nearest last
4. explicit user chat instructions

Each injected block states that explicit user messages override the file guidance.

### 4.3 Delivery order

- Global and root blocks are placed in the system prompt, global first.
- Nested blocks are appended to the string result of the filesystem tool that touched the path, root-to-leaf, nearest last.

## 5. Instruction loader

Create `packages/agentbox-api/src/agentbox_api/project_instructions.py`.

### 5.1 Types

```py
MAX_INSTRUCTION_BYTES = 32 * 1024

@dataclass(frozen=True)
class InstructionFile:
    path: pathlib.Path
    source: str       # "~/AGENTS.md", "AGENTS.md", "packages/web/AGENTS.md"
    scope: str        # "global", "project", "nested"
    content: str
    truncated: bool

@dataclass
class InstructionState:
    delivered: dict[pathlib.Path, str]  # path -> sha256
    root_hash: str | None
    global_hash: str | None
```

The exact private fields may vary, but the public behavior must match this spec.

### 5.2 Loading rules

- Read UTF-8 with `errors="replace"`; log a warning when replacement occurs.
- Empty or whitespace-only files are ignored.
- Read at most the remaining budget plus one byte to detect truncation.
- Truncate on a valid UTF-8 byte boundary and append an explicit truncation notice.
- Resolve paths with `Path.resolve()`.
- Global must resolve under the server user's home directory.
- Project root and nested files must resolve under the project root.
- Reject and log paths that escape their boundary.

### 5.3 Formatting

```text
<project_instructions source="AGENTS.md" scope="project">
...content...
</project_instructions>
```

Use the same wrapper for global and nested blocks. Add a short preface in the system prompt:

> Project instructions follow. Explicit user messages override them.

## 6. Root and global refresh

- `prepare_agent` re-reads global and root guidance on every user run.
- It composes a system-prompt block after the agent instructions and skill catalog.
- If root or global content changes, the new content is used for that run.
- If the file is removed, its block is omitted and its cached content is cleared.
- If reading fails:
  - use the last known content from the process-local cache when available;
  - otherwise omit the block and log the failure.
- No watcher is used.

## 7. Nested discovery

### 7.1 Tool hook

Add a project-instructions tool hook, built per session and registered alongside the existing LSP hook.

Eligible tools are the string-returning filesystem tools with a path arguments, including:

- `read_text_file`
- `read_file`
- `read_multiple_files`
- `list_directory`
- `list_directory_with_sizes`
- `search_files`
- `write_file`
- `append_file`
- `edit_file`
- `create_directory`
- `move_file`
- `copy_file`
- `delete_path`

For `read_multiple_files`, handle each path. For move/copy tools, consider both source and destination.

Non-string-returning tools such as `get_file_info` and `directory_tree` are not used for nested injection because the registry only appends hook output to string results. A later read/list/write in that directory delivers the guidance.

### 7.2 Candidate walk

For a touched file or directory:

- start at the file's parent (or the directory itself);
- walk upward to the project root;
- exclude the project root;
- collect existing `AGENTS.md` files;
- order root-to-leaf, nearest last.

Do not follow extra roots or skill directories.

### 7.3 Delivery state

- Per-session state tracks each delivered nested path and its content hash.
- Skip unchanged files already delivered in this session.
- Re-deliver a changed file with an update notice.
- If a previously delivered nested file disappears, deliver a removal notice.
- On read failure, keep the last known state and do not deliver a removal.
- State is process-local and cleaned up when the session is deleted.

### 7.4 Nested refresh timing

Nested files are re-read only when a tool touches their directory again. Changes are not detected proactively and do not mutate a system prompt already sent.

## 8. Budget

- Shared 32 KiB per session.
- Allocation order: root -> previously delivered nested -> global.
- New nested files consume remaining budget as they are discovered.
- On the turn a new nested file is discovered, the already-sent system prompt is not mutated. If the nested file does not fit, truncate it with a notice or omit it with a budget-exhausted notice.
- Global content may shrink or disappear on later turns when project guidance consumes the budget. Log the change and include a small omission notice in the next system prompt.
- The budget is measured in UTF-8 bytes.

## 9. Subagents

- Background sub-sessions call `prepare_agent`; they receive global and root guidance and maintain their own nested state.
- In-process subagent specs inherit the parent project-instructions block.
- Nested guidance is delivered through the same tool hook when the subagent touches project paths.
- Each sub-session has its own 32 KiB budget.

## 10. Logging

Log structured events:

- global/project/nested instructions loaded;
- content changed;
- file removed;
- file truncated;
- budget exhausted;
- read failure with last-known-content reuse;
- symlink escape rejected.

Do not log full instruction content at info level. Debug-level content logging is allowed only if it cannot expose secrets; prefer source path, byte count, and hash.

## 11. Testing

### 11.1 Loader unit tests

- missing, empty, valid, and large files;
- truncation notice and valid UTF-8 boundary;
- invalid UTF-8 handled without crashing;
- global/project symlink escape rejected;
- removal clears;
- read failure preserves last known content.

### 11.2 Nested discovery tests

- file target and directory target;
- root exclusion;
- nearest-last ordering;
- deduplication;
- changed file re-delivery;
- removed file notice;
- read failure does not emit removal;
- budget pressure and omission.

### 11.3 Integration tests

- `prepare_agent` includes global and root guidance;
- a changed root is visible on the next run;
- root removal clears guidance;
- nested instructions are appended to a read result;
- non-string tools do not receive nested instructions;
- background sub-sessions receive root guidance;
- session deletion clears instruction state.

### 11.4 Acceptance checks

- No instruction content is injected when files are absent.
- Project root outranks global.
- Nearest nested file appears last.
- User chat remains explicitly higher precedence.
- Prompt size never exceeds the 32 KiB budget.
- Existing chat, ACP, A2A, sub-session, and tool tests remain green.

## 12. Risks and trade-offs

- **Prompt injection:** AGENTS.md is project-owned content and is treated as instructions. Explicit user chat can override it, but a malicious project file can still influence behavior. This is inherent to the format.
- **Dynamic budget:** nested discovery can shrink global guidance on later turns. This is intentional project priority; logging and omission notices make it visible.
- **Process-local state:** multiple workers can duplicate nested delivery. Delivery is idempotent within a session and bounded by the budget.
- **Nested refresh latency:** a nested change is only noticed when its directory is touched again.
- **Tool-result injection:** nested guidance is not part of the system prompt. It is delivered as an instruction update in tool output, matching discovery-based agents.

## 13. Acceptance criteria

- Global, project, and discovered nested AGENTS.md guidance reaches the agent.
- Nested files follow nearest-last precedence.
- Root/global changes apply on the next user run; removal clears; read failure preserves.
- Subagents receive the same guidance.
- The shared 32 KiB budget is enforced with root -> nested -> global priority.
- Symlink escapes are rejected.
- No new UI or database migration is required.
- All backend package tests, frontend tests/build, and E2E remain green.
