# Automatic LSP Diagnostics — Comparative Study and Efficiency Review

Date: 2026-11-22
Status: Research spike / study. No implementation is proposed for commitment here.
Scope: How agentbox currently attaches LSP diagnostics to file edits, how other
agent harnesses do or do not do it, and which changes are most likely to make
agentbox faster and more reliable.

Related agentbox docs:

- `docs/superpowers/specs/2026-11-19-lsp-diagnostics-design.md`
- `docs/superpowers/specs/2026-11-21-rust-lsp-quiescence-design.md`

---

## 1. Executive summary

Agentbox runs diagnostics **synchronously inside the write tool call**, on
**every** `write_file`/`append_file`/`edit_file`, and the model cannot proceed
until the wait completes. The wait is bounded by a settle/quiescence heuristic
capped by `lsp_diagnostics_timeout` (5 s by default; Rust declares a 15 s settle
that the 5 s cap currently overrides). Cold starts add up to 10 s of LSP
initialization. Tool provisioning can additionally download `uvx ty` /
`npx typescript-language-server` on the first edit.

Three conclusions from the comparison:

1. **The blocking-in-the-write-tool shape is the main efficiency problem**, and
   it is the part most other harnesses either avoid or heavily soften. Opencode
   and Crush do block, but only for a short bounded window (3 s / adaptive
   ≤5 s), and both also expose an **on-demand** diagnostics tool. Claude Code
   treats LSP as a tool plus auto-attached diagnostics with explicit timeouts;
   VS Code-native agents read the editor's already-computed diagnostics. Pi,
   Aider, Codex CLI and Gemini CLI deliberately have **no built-in blocking LSP
   path** and use lint/typecheck/test commands instead.
2. **Most of agentbox's reliability risk is in the client/manager plumbing, not
   in the LSP idea.** The most concrete defects are: an undrained stderr pipe
   (a classic child-process deadlock, especially with rust-analyzer), monorepo
   root selection based on a global recursive scan instead of the nearest
   project root for the edited file, single-slot waiter maps that concurrent
   writes can clobber, and no `didClose`/LRU bound on open documents.
3. **LSP is a "nice extra", not a source of truth.** The opencode docs say this
   explicitly and recommend running project lint/typecheck commands instead
   when they are available. The strongest long-term agentbox design is likely a
   **background, best-effort LSP hint pipeline plus an explicit project check
   command**, not a mandatory synchronous LSP step on every edit.

Recommended direction (detailed in §6): keep LSP, but make it **asynchronous and
optional**, add an **on-demand `lsp_diagnostics` tool**, make the auto-attached
payload a **small edited-file-only error summary**, and fix the client plumbing
first. Treat "run the project's own check command" as a first-class fallback.

---

## 2. How agentbox works today

Code:

- `packages/agentbox-harness/src/agentbox_harness/lsp/hooks.py`
- `packages/agentbox-harness/src/agentbox_harness/lsp/manager.py`
- `packages/agentbox-harness/src/agentbox_harness/lsp/client.py`
- `packages/agentbox-harness/src/agentbox_harness/lsp/stacks.py`
- `packages/agentbox-harness/src/agentbox_harness/lsp/detect.py`
- `packages/agentbox-harness/src/agentbox_harness/lsp/quiescence.py`
- Hook wiring: `packages/agentbox-api/src/agentbox_api/skills.py:229`,
  `packages/agentbox-harness/src/agentbox_harness/tools/registry.py:43`

### 2.1 Flow

1. `ToolRegistry.register_native` wraps every native tool call. After the tool
   returns, each hook is awaited (`registry.py:43-72`).
2. `make_lsp_hook` runs only for `write_file`, `append_file`, `edit_file`
   (`hooks.py:4,29`).
3. It picks the first detected stack whose extensions match the path
   (`hooks.py:34-41`).
4. `manager.get_or_start(project_root, stack)` lazily spawns and initializes a
   server (`manager.py:39-73`).
5. `server.sync_document(path, language)` sends `didOpen`/`didChange`
   (`client.py:213-239`), and for Rust also `didSave` (`hooks.py:49-50`).
6. `server.diagnostics(path)` either pulls `textDocument/diagnostic`, or waits
   for `publishDiagnostics` (`client.py:248-320`).
7. Errors/warnings (severity 1/2) are formatted, capped at 10, and appended to
   the tool's string result (`hooks.py:7-24`, `registry.py:70-71`).

### 2.2 Where the time goes

| Stage | Current behaviour | Cost / risk |
|---|---|---|
| Stack detection | `detect_stacks` runs `root.glob(marker)` for every marker of every stack, then filters matches (`detect.py:15-25`) | `**/*.py` and `**/package.json` traverse `node_modules`, `.venv`, `target`, etc. before filtering. Cached per project root, but first call is an unbounded full walk. |
| Server provisioning | Commands are `uvx ty server` and `npx -y typescript-language-server@latest` (`stacks.py:18-37`) | First edit may download packages from the network. `@latest` drifts. This happens inside a tool call. |
| Initialize | Up to `lsp_initialize_timeout=10 s` (`config.py:31`, `client.py:81-92`) | Rust-analyzer cold start (cargo metadata / proc-macro build) commonly approaches or exceeds this. |
| Sync | Full file text read + `didOpen`/`didChange` (`client.py:213-239`) | Full-text sync; no incremental range edits. Usually small. |
| Diagnostics | Pull request with `lsp_diagnostics_timeout=5 s`; push settle `min(timeout, settle)`; Rust quiescence wait (`client.py:248-320`) | Rust: 5 s worst case per edit after warm-up. Other push stacks: up to 5 s. Pull stacks: one request round trip. |
| Total (cold Rust edit) | detection + download/init + analysis | ~10–20 s and can time out. |
| Total (warm clean Rust edit) | quiescence/settle wait | up to 5 s if no publish and no busy toggle is observed. |

### 2.3 Reliability issues observed in the code

These are ordered roughly by likely impact.

1. **Undrained stderr pipe.** `stderr=asyncio.subprocess.PIPE` is set
   (`client.py:67-73`) but never read. rust-analyzer is very chatty on stderr;
   when the OS pipe buffer fills, the child blocks on write, stops processing
   LSP messages, and agentbox waits until timeout. This alone can explain
   intermittent "Rust diagnostics hang / are missing" reports. `npx`/`uvx`
   download progress also writes to stderr.
2. **Wrong root for monorepos.** Detection scans the whole `project_root`, but
   the server is always initialized with `rootUri = project_root`
   (`client.py:75-92`). In a repo with `apps/web/package.json` or nested Cargo
   crates, tsserver/rust-analyzer is started at the wrong root, which is both
   slower and less accurate. Opencode and Crush resolve the **nearest** root
   from the edited file (see §3.1, §3.2).
3. **Global recursive scan instead of lazy root resolution.** The design doc
   says `os.walk` with pruning; the implementation globs first and filters
   afterward, so pruned directories are still traversed. `detect_stacks` is
   also all-or-nothing per project, not per edited file.
4. **Concurrent writes clobber waiters.** `_diagnostic_events` is keyed by path
   with a single `asyncio.Event` (`client.py:52-53,266-288,290-320`). Two
   concurrent hooks for the same file overwrite each other's event; one waits
   until its timeout. Document versions can also interleave because
   `sync_document` is not serialized per server beyond the write lock.
5. **No `didClose`, no LRU.** Open documents are never closed and
   `_diagnostics`/`_publish_counts`/`_versions` grow for the process lifetime
   (`client.py:51-54`). Claude Code explicitly added a 50-document LRU to fix
   this class of leak.
6. **Transient failure disables a stack for 60 s.** Any init exception records
   `_failed[(root, stack)]` and suppresses retries for
   `lsp_failure_backoff_seconds=60` (`manager.py:43-47,65-73`). A one-off slow
   cold start is indistinguishable from a broken server.
7. **Dead servers are replaced, not stopped.** `get_or_start` creates a new
   `LspServer` when the old one is `dead` and overwrites the map entry
   (`manager.py:48-64`); the old process/reader is not explicitly stopped.
8. **Narrow server-request handling.** `workspace/configuration` always returns
   `[{}]`, dynamic capability registration is answered with `None`, and
   `workspace/applyEdit`, `window/showDocument`, `window/showMessageRequest`,
   `$/progress`, `workspace/workspaceFolders` are not handled
   (`client.py:143-167`). Fine for the current three servers; fragile for the
   next one.
9. **No watched-file notifications.** Only the edited path is synced; changes
   that affect other files are not announced (`workspace/didChangeWatchedFiles`
   is never sent). Cross-file diagnostics can stay stale.
10. **Session bookkeeping grows.** `_active[session_id]` is never pruned
    (`manager.py:75-94`), and there is no per-project shutdown until app exit
    (`manager.py:99-108`).

### 2.4 Why the Rust quiescence work did not fully fix it

The quiescence design (`2026-11-21-rust-lsp-quiescence-design.md`) correctly
identified that waiting for the full settle window is wasteful. But the
implemented wait still:

- falls back to the settle loop for any clean file that produces neither a
  publish nor a `quiescent:false` toggle, which is the documented "rare" case
  but is a real 5 s stall when it happens;
- is capped by `lsp_diagnostics_timeout=5` even though the Rust stack declares
  `settle=15` (`client.py:259`), so the semantics are confusing;
- still runs inline in the write tool, so warm-up and server contention show up
  directly as user-visible edit latency.

---

## 3. How other harnesses do it

### 3.1 Opencode (v1.0.0 tag)

Sources:
`packages/opencode/src/lsp/{index,client,server,language}.ts`,
`packages/opencode/src/tool/{write,edit,lsp-diagnostics,lsp-hover}.ts`.
Docs: `https://opencode.ai/docs/lsp/`.

Mechanics:

- **Push diagnostics only.** The client subscribes to
  `textDocument/publishDiagnostics`, caches per path, and publishes an internal
  `lsp.client.diagnostics` bus event. It does not use pull diagnostics.
- **Per-file nearest-root discovery.** Each server entry has a `root(file)`
  function (e.g. TypeScript walks up to the nearest lockfile; Rust walks from
  the nearest `Cargo.toml` up to a workspace root). The client cache is keyed by
  `(root, serverID)`.
- **Lazy start on touch.** `touchFile(path, waitForDiagnostics)` starts all
  servers that handle the extension, sends `didOpen`/`didChange`, and if
  requested waits **3 s** for *any* publish for that path. Spawn errors are
  cached as "broken" per `(root, serverID)`.
- **Write/edit tools append diagnostics.** After writing, `write` waits for the
  file's publish, then calls `LSP.diagnostics()` (all cached diagnostics across
  all servers) and appends:
  - `write`: the edited file under `<file_diagnostics>` ("This file has errors,
    please fix") with **all severities**, plus every other file under
    `<project_diagnostics>`;
  - `edit`: only the edited file, filtered to **severity 1**.
  The two tools are not consistent, which is itself a sign of how easily this
  payload shape drifts.
- **Separate on-demand tools.** `lsp_diagnostics` (path argument) and
  `lsp_hover` let the model ask explicitly. They also call `touchFile(..., true)`
  and then read cached diagnostics.
- **No `didClose`.** Documents stay open for the instance lifetime. No LRU.
- **Docs stance.** "LSP is disabled by default. When enabled, servers start when
  one of the above file extensions is detected and the requirements are met."
  The "Best Practices" section is unusually candid: language servers get out of
  sync, consume memory, vary by version, and slow workflows; "In many projects
  it is better to have the agent run lint, typecheck, or other diagnostic CLI
  tools directly." OpenCode recommends documenting those commands in
  `AGENTS.md`/skills.

Takeaways: nearest-root resolution, a short fixed wait, edited-file diagnostics
first (with a severity filter that is inconsistent between `write` and `edit`),
project diagnostics as secondary and only on `write`, and an on-demand tool.
Even so, they now recommend LSP as opt-in.

### 3.2 Crush (charmbracelet/crush, main, 2026-11-22)

Sources:
`internal/lsp/{client,manager}.go`,
`internal/agent/tools/{diagnostics,edit,view}.go`.

Mechanics:

- **Lazy start by file type + root markers.** `Manager.Start(path)` finds
  servers that `handles(filetype)` and whose root markers exist, with
  auto-start gating and a 30 s init timeout.
- **Auto diagnostics after edit** (`edit.go:96-100`): `notifyLSPs` starts the
  server, calls `OpenFileOnDemand`, `NotifyChange`, and then waits for
  diagnostics **in parallel across all matching clients**, up to 5 s.
- **Adaptive wait** (`client.go:620-690`): return after **1 s** if the
  diagnostics version has not changed at all; once it changes, wait until the
  version is stable for **300 ms**; hard deadline 5 s. This is the most
  efficient blocking algorithm among the ones studied.
- **Output shape** (`diagnostics.go`): `<file_diagnostics>` (all severities,
  errors first, capped at 10) + `<project_diagnostics>` (same) +
  `<diagnostic_summary>` with "Current file: N errors, M warnings / Project: …".
- **On-demand tool** `lsp_diagnostics` with an optional `file_path`; empty path
  refreshes all open files, sends `workspace/didChangeWatchedFiles`, and waits
  up to 5 s per client.
- **Reads also open in LSP** (`view.go:247-257`): `openInLSPs` starts servers
  and opens the file, then waits only **300 ms** for diagnostics before
  returning the file plus any cached diagnostics. This warms servers and catches
  pre-existing errors on read.
- **State machine + restart.** `StateUnstarted/Starting/Ready/Error/Stopped`;
  `Restart()` closes, re-creates, re-initializes (30 s), waits for ready, and
  reopens files. `KillAll`/`StopAll` distinguish fast kill from graceful stop.
- **Versioned diagnostic map** (`csync.VersionedMap`) and a diag-counts cache
  versioned for cheap UI/context updates.
- **`didClose` exists** (`CloseAllFiles`), but I did not find an LRU cap.

Takeaways: adaptive settle (1 s no-change early exit, 300 ms stability) is a
good model for agentbox; parallel per-client waits; summary counts; read-side
warm-up; explicit restart.

### 3.3 Claude Code (Anthropic, closed source; public changelog)

Source: `anthropics/claude-code` `CHANGELOG.md` (main, 2026-11-22), docs.

Mechanics and lessons visible in the changelog:

- **LSP is a tool** ("Added LSP tool for code intelligence features like
  go-to-definition, find references, and hover documentation"). Diagnostics are
  also attached automatically after edits, but the changelog repeatedly refers
  to **"LSP diagnostic summaries"** that expand on click, not raw dumps.
- **VS Code integration exposes an on-demand diagnostics tool** so the agent can
  read the Problems panel "at any time, not only right after it edits a file".
- **Timeouts are explicit and per server:** `startupTimeout`, and later a
  per-server `requestTimeout` defaulting to 60 s after LSP tool calls could hang
  indefinitely on dynamic capability registration or unresponsive servers.
- **Document memory is bounded:** "LSP documents staying open indefinitely (now
  LRU with 50-doc cap)".
- **Project-wide publish storms are a known perf hazard:** fixed "per-turn
  slowdown when a language server publishes project-wide diagnostics for
  thousands of files" and "multi-second UI stalls after editing a file with
  thousands of IDE diagnostics".
- **Staleness is a known correctness hazard:** fixed "LSP diagnostics from
  before an edit appearing after it, causing the model to re-read files it just
  edited".
- **Startup races are real:** fixed "LSP tool calls and diagnostics failing when
  several calls or edits arrived while a language server was still starting",
  and "race condition where LSP tool could return 'no server available' during
  startup".
- **Crash recovery:** "LSP server zombie state after crash — server now restarts
  on next request instead of failing until session restart".
- **Escape hatch:** `--bare` "skips hooks, LSP, plugin sync, and skill directory
  walks" for scripted runs.
- **Health:** fixed "a plugin LSP server that fails to initialize preventing a
  valid LSP server from another plugin handling the same file extension".

Takeaways: even a mature implementation with dedicated engineers needed years of
hardening around startup races, stale diagnostics, request timeouts, doc leaks
and publish volume. Agentbox should assume the same failure modes and design
for them explicitly (bounded requests, version/generation checks, restarts,
LRU, project-wide smoothing), rather than treating LSP as a solved dependency.

### 3.4 Pi (earendil-works/pi, formerly badlogic/pi-mono)

Source: `earendil-works/pi` (main, 2026-11-22). The tree has no LSP package or
LSP tool. `packages/coding-agent/src/core/diagnostics.ts` is about
extension/skill/prompt resource diagnostics (collisions, warnings), not LSP.

Ecosystem: `samfoy/pi-lsp-extension` adds LSP integration to Pi as an
**extension** with on-demand diagnostics, hover, definition, references,
symbols, and rename.

Takeaway: Pi keeps the core agent tiny and pushes LSP to an optional,
model-invoked extension. No automatic blocking diagnostics on every write.

### 3.5 Aider

Source: `Aider-AI/aider` docs `usage/lint-test.md`.

- No LSP. After edits, Aider can run **lint** and **test** commands and feed
  stdout/stderr back into the loop.
- `--lint-cmd`, `--auto-lint`, `--lint "language: cmd"`, `--test-cmd`,
  `--auto-test`. Lint defaults to on for edited files; tests are opt-in.
- The docs explicitly describe using a lint command that also compiles
  (e.g. a script) and a test command that also builds.

Takeaway: the project's own check command is the feedback signal. This is
cheap, deterministic, CI-aligned, and works for every language. It trades
incrementality for reliability.

### 3.6 VS Code-native agents (Cline, Roo/Kilo, Continue)

These agents live inside the editor extension host. They read diagnostics that
the editor's already-running language servers have computed
(`vscode.languages.getDiagnostics()`), and can also request hovers, definitions
and references through the editor API. Consequences:

- No duplicate LSP process, no cold start in the agent, no init timeout.
- Diagnostics may be stale relative to an edit unless the agent waits for the
  editor to re-analyze, but the editor owns that lifecycle.
- The human already sees the same Problems panel, so the agent and user share a
  source of truth.

Third-party bridges externalize the same idea for CLI agents:

- `tjx666/vscode-mcp`: MCP server/CLI that exposes `get_diagnostics`,
  `get_symbol_lsp_info`, `get_references`, rename, backed by the running VS
  Code instance over a per-workspace socket. Explicit motivation: avoid slow
  `tsc`/`eslint` runs.
- `carldaws/squiggles`, `AlteredCraft/lsp4agents`, `harshav167/lspd`
  ("errors surface after every file write and read, no IDE needed"),
  `Jaylor-Wang/agent-lsp` (lightweight zero-dependency LSP client/CLI).

Takeaway: the "editor owns the server, the agent asks on demand" split is a
proven architecture. Agentbox is headless/web, so it cannot assume an editor,
but it can copy the *on-demand tool* shape and expose diagnostics in the chat
UI like a Problems panel.

### 3.7 CLI agents without LSP (Codex CLI, Gemini CLI)

Their READMEs do not document built-in LSP integration; the agent loop relies on
shell commands (tests, typecheckers, linters) and file tools. This is consistent
with the Aider/Pi philosophy and with opencode's own current recommendation.

---

## 4. Comparison matrix

| Harness | Server ownership | Auto after edit? | Wait strategy | On-demand tool? | Per-file nearest root? | Doc lifecycle | Enablement |
|---|---|---|---|---|---|---|---|
| **agentbox** | In-process manager, shared per `(project, stack)` | Yes, synchronous | Pull request; push settle/quiescence, cap 5 s (Rust settle 15 s) | No | No (project root only) | Never closes; unbounded | On by default |
| **opencode v1** | In-process, per `(root, server)` | Yes, synchronous | 3 s for any publish | Yes (`lsp_diagnostics`, `lsp_hover`) | Yes | Never closes; no LRU | Disabled by default; docs recommend CLI checks |
| **Crush** | In-process, per `(root, server)` | Yes, synchronous | Adaptive: 1 s no-change exit, 300 ms stability, 5 s cap; parallel | Yes (`lsp_diagnostics`) | Yes (root markers) | `didClose`; no LRU found | Config per server |
| **Claude Code** | In-process, plugin-provided servers | Yes, summaries; plus IDE Problems | Explicit startup/request timeouts (60 s request default); project-wide smoothing | Yes (LSP tool; VS Code diagnostics tool) | Presumably | LRU 50 docs | Opt-in plugins; `--bare` skips |
| **Pi** | None | No | — | Extension only | — | — | Extension |
| **Aider** | None | Lint/test commands | Command runtime | No | — | — | Opt-in |
| **VS Code agents** | Editor | Editor-driven | Editor-driven | Yes via editor API | Editor | Editor | Editor |
| **Codex/Gemini CLI** | None | No | — | No | — | — | Shell commands |

---

## 5. Cross-cutting principles

1. **LSP is best-effort, stateful, and often wrong.** Treat every diagnostic as
   a hint with a version and a timestamp, never as ground truth. Prefer the
   project's own check command when it exists.
2. **Do not put an unbounded stateful service on the critical path of a write.**
   Either bound the wait aggressively or move it off the tool result.
3. **Pull > push when available.** A request has a clear completion; push
   requires settle heuristics. Rust is the exception (push + `serverStatus`).
4. **Return fast when nothing is happening.** Crush's 1 s no-change exit is a
   good pattern; agentbox currently waits the full window in exactly the clean
   case.
5. **Only the edited file's errors belong in an automatic payload.** Project-wide
   diagnostics cause token bloat, staleness, and model re-reads (Claude Code had
   to fix this explicitly). Project diagnostics belong behind an on-demand tool
   or a UI panel.
6. **Resolve roots from the edited file upward.** Do not spawn a monorepo-wide
   server because some nested folder has a `package.json`.
7. **Bound every resource:** open documents, diagnostics cache, waiters,
   request duration, startup duration, number of servers, sessions tracked.
8. **Make failure visible and recoverable:** health/status, restart on crash,
   short retry for transient failures, a single escape hatch to disable LSP.
9. **Prefer incremental delivery:** diagnostics can land in the next turn or in
   the UI rather than in the same tool result.
10. **Warm up deliberately, not opportunistically.** If the first `.rs` write
    pays rust-analyzer's cold start, start it when the session opens a Rust
    project (or on first read), not inside the first write.

---

## 6. Recommendations for agentbox

No implementation is committed here. These are candidate directions with
trade-offs, ordered by expected value per unit of risk.

### 6.1 Fix the plumbing first (low risk, high reliability payoff)

These are bugs, not architecture changes, and should be evaluated before any
redesign:

1. **Drain stderr.** Continuously read and debug-log the child's stderr (or
   redirect it to a file/devnull). This is the highest-probability fix for
   Rust hangs. Add a regression test with a fake server that floods stderr past
   the pipe buffer and still answers diagnostics.
2. **Nearest-root resolution.** Compute the server root from the edited file
   (walk up to the nearest `pyproject.toml`/lockfile/`Cargo.toml`/workspace
   marker), cache per directory, and key servers by `(root, stack)`. Stop doing
   a project-wide recursive detection on the first edit.
3. **Version-aware, multi-waiter diagnostics.** Replace the single
   `_diagnostic_events[path]` event with a set of waiters, record a publish
   generation per path, and only accept a publish whose generation is newer than
   the write. This fixes concurrent-write clobbering and stale pre-edit
   diagnostics.
4. **Serialize per-server document sync.** A per-server `asyncio.Lock` around
   `sync_document` + `didSave` prevents interleaved `didChange` versions.
5. **`didClose` + LRU.** Close documents that have not been touched in a while
   and cap open docs per server (Claude Code uses 50). Bound `_diagnostics`,
   `_publish_counts`, and `_versions` to open/known docs.
6. **Separate startup and request budgets; retry transient failures.** Do not
   blacklist a stack for 60 s because a cold start was slow. Use exponential
   backoff with a short first retry, surface health, and restart on crash.
7. **Stop dead servers explicitly** and prune `_active` per session. Add
   per-project shutdown when the last session closes.
8. **Provision deterministically.** Remove `@latest` from the default server
   commands, pin versions, and avoid network downloads inside a tool call.
   Either require the binary on `PATH` or warm/install it at session start with
   progress surfaced to the user.

### 6.2 Make the hot path cheap (medium risk)

Candidate A — **On-demand tool + tiny auto-summary** (recommended first step):

- Add a native `lsp_diagnostics` tool (path optional; empty means project) that
  opens/syncs files on demand, waits briefly, and returns full details.
- After a write, attach only **the edited file's severity-1 errors**, capped at
  a small number (e.g. 5), with a one-line header pointing to the tool for
  details. Do not attach project-wide diagnostics.
- Consider a `<diagnostic_summary>` count line (Crush style) instead of a list.

Candidate B — **Background diagnostics pipeline** (better latency, more moving
parts):

- After a write, mark the path dirty and return immediately.
- A per-server background worker coalesces dirty paths, syncs documents, waits
  adaptively (Crush's 1 s/300 ms/5 s), and stores results with a generation.
- Deliver results as a system reminder / next-turn note / UI event, not by
  blocking the write. The model can also call `lsp_diagnostics` to pull the
  latest.
- Requires a way to inject context outside the tool result (agentbox already
  streams events and has a frontend event bus).

Candidate C — **CLI-first, LSP-second**:

- Detect the project and run a configured check command (`cargo check`,
  `tsc --noEmit`, `uv run ty check`, etc.) either on demand, at end of turn, or
  via a user-configured command. Keep LSP for fast single-file hints when it is
  already warm.
- Most reliable and CI-aligned; least incremental. Aider/opencode/Pi all lean
  this way.

Recommendation: ship A first (small, immediately useful), then evaluate B for
the auto path. Keep C as the explicit fallback and document it in `AGENTS.md`
and project onboarding.

### 6.3 Product stance and configuration

- **Default LSP off for new projects, or at least off for Rust**, with an
  explicit opt-in and a visible status in the session About panel. Opencode's
  docs now recommend opt-in for good reasons.
- **Per-stack enable/disable, timeouts, and readiness strategy** already exist in
  `lsp_servers_json`; expose the important ones in the UI and document the
  escape hatch. Add a global "bare" mode that skips LSP for scripted runs.
- **Health and metrics** in the About panel: server state, open docs, last
  publish age, last error, average wait. This turns "unreliable" into
  observable.

### 6.4 What *not* to do

- Do not add more stacks or features (hover/references/code actions) before the
  plumbing and hot path are fixed.
- Do not keep increasing `lsp_diagnostics_timeout`; raising the cap hides the
  problem and makes edits slower.
- Do not rely on `@latest` tool downloads during a tool call.
- Do not append project-wide diagnostics to every edit; it is token-expensive and
  makes stale state more likely.
- Do not add aliases or parallel mechanisms: if a new path is chosen, replace the
  old hook cleanly (consistent with `AGENTS.md` "replace, don't layer").

---

## 7. Measurement plan for the next phase

Before choosing between 6.2 A/B/C, instrument the current path:

- Per edit: detection time, spawn time, initialize time, sync time, first
  publish/response time, settle time, total hook time.
- Counts: timeouts, empty-result returns, non-empty results, server restarts,
  backoff hits, concurrent waits on the same path.
- Real-server scenarios: cold Rust project, warm Rust clean edit, warm Rust
  error edit, nested TS monorepo, Python `ty`, server killed mid-session,
  server that floods stderr.
- Budgets to aim for: automatic path adds **< 150 ms p95** to a write when warm
  and **0 ms** when cold (diagnostics arrive asynchronously); on-demand tool
  returns within 1–5 s with a clear timeout; zero indefinite hangs.

Existing tests to extend:

- `packages/agentbox-harness/tests/test_lsp_client.py`
- `test_lsp_manager.py`
- `test_lsp_hook.py`
- `test_lsp_quiescence.py`
- `test_lsp_real.py`
- `packages/agentbox-api/tests/test_session_lsp.py`

Note that `test_lsp_real.py` currently uses a 60 s provisioning timeout and a
60 s settle for Rust, which masks the cold-start problem rather than measuring
it.

---

## 8. Open questions for a future design spec

1. Where should asynchronously produced diagnostics be delivered—next tool
   result, a system reminder before the next model call, or only via the UI and
   an on-demand tool?
2. Should the automatic path ever include warnings, or only errors (severity 1)?
3. Is a project check command a first-class agentbox feature (configured per
   project) or left to `AGENTS.md`/skills?
4. What is the desired default for Rust specifically, given flycheck latency and
   cold-start cost?
5. Do we need multi-root/workspace support (e.g. Cargo workspace members,
   pnpm workspaces), or is nearest-root per file sufficient?
6. How much of the About/health surface is worth building before the next
   redesign?
7. Should agentbox ever consume an editor/external LSP bridge (ACP/IDE/MCP)
   instead of spawning servers itself?

---

## 9. References

Agentbox:

- `packages/agentbox-harness/src/agentbox_harness/lsp/` (all modules)
- `packages/agentbox-harness/src/agentbox_harness/tools/registry.py`
- `packages/agentbox-api/src/agentbox_api/skills.py`
- `packages/agentbox-api/src/agentbox_api/config.py`
- `docs/superpowers/specs/2026-11-19-lsp-diagnostics-design.md`
- `docs/superpowers/specs/2026-11-21-rust-lsp-quiescence-design.md`

Opencode (v1.0.0 tag):

- `packages/opencode/src/lsp/index.ts`, `client.ts`, `server.ts`, `language.ts`
- `packages/opencode/src/tool/write.ts`, `edit.ts`, `lsp-diagnostics.ts`
- https://opencode.ai/docs/lsp/

Crush (main):

- `internal/lsp/client.go`, `manager.go`
- `internal/agent/tools/diagnostics.go`, `edit.go`, `view.go`

Claude Code changelog (main):
- https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md
- Relevant entries: LSP tool introduction; `startupTimeout`; per-server
  `requestTimeout` 60 s; 50-doc LRU; project-wide diagnostics slowdowns;
  stale-pre-edit diagnostics; startup races; zombie-server restart; VS Code
  on-demand diagnostics; `--bare`.

Pi:
- https://github.com/earendil-works/pi (no built-in LSP)
- `samfoy/pi-lsp-extension` (third-party on-demand LSP tools)

Aider:
- https://aider.chat/docs/usage/lint-test.html

VS Code / external bridges:
- `tjx666/vscode-mcp` (real-time LSP diagnostics via VS Code)
- `carldaws/squiggles`, `AlteredCraft/lsp4agents`, `harshav167/lspd`,
  `Jaylor-Wang/agent-lsp`
