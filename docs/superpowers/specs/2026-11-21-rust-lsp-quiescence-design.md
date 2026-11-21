# Rust LSP Quiescence Readiness — Design

Date: 2026-11-21
Status: Approved (design), spec awaiting review.
Roadmap: D19 — Rust LSP latency.

## Goal

Make write/edit tool results in Rust projects return as soon as rust-analyzer's
native analysis is quiescent, instead of always blocking for the push-mode
settle window. Keep `didSave` so diagnostics are still triggered. Preserve the
existing behavior for every other stack, and leave a clean seam for future
language servers (e.g. gopls) that expose a different readiness signal.

Intent in one line: **faster hints/diagnostics for Rust projects**, without
regressing other stacks.

## Background

Today the Rust stack is `pull=False, save=True, settle=15.0`. After a write the
hook sends `didOpen`/`didChange`, then `didSave`, then waits for a
`publishDiagnostics` notification. The wait is:

```python
grace = min(self.diagnostics_timeout, self.settle)
```

so with the default `lsp_diagnostics_timeout=5.0` the effective window is 5 s,
not 15 s. The loop ignores empty publishes and keeps waiting until a non-empty
publish or the deadline. A clean Rust file therefore blocks for the full window
on every write, even though rust-analyzer has finished its analysis much
earlier.

rust-analyzer exposes an experimental readiness signal:
`experimental/serverStatus`, a server→client notification
`{health: "ok" | "warning" | "error", quiescent: boolean, message?: string}`,
gated behind the experimental **client** capability
`{ "serverStatusNotification": true }`. The current client drops all
unrecognized notifications.

Two diagnostic sources matter:
- **native rust-analyzer analysis** — fast; done when the server reports
  quiescent;
- **flycheck / cargo check** — slower; can report borrow-check/compiler-only
  diagnostics after quiescence.

This design stops waiting at quiescence. Flycheck-only diagnostics that arrive
later are not awaited.

## Decisions

- **Stack-configured readiness strategy**, not a Rust special-case in the
  client. `LspStack` gains `quiescence: str | None = None`; only the Rust
  default sets `"server_status"`. Any stack can opt in via defaults or
  `lsp_servers_json`.
- **One tracker implementation now** (`ServerStatusTracker`). No strategy
  hierarchy; the `quiescence` field + tracker boundary is the reuse seam for
  future values.
- **Return at quiescence** (no post-quiescence grace). Clean writes return
  immediately; flycheck-only diagnostics may be missed on that write.
- **Fallback to the existing settle loop** whenever no `serverStatus` has been
  seen. Behavior for `quiescence=None` stacks is unchanged, byte-for-byte.
- **Health is log-only.** Use only `quiescent` for timing; log, and warn when
  health is not `ok`. No API or UI change.

## Architecture

No new process lifecycle, subclass, or server mode. The same `LspServer` and
`LspManager` are used. The strategy only affects the push-mode wait inside
`diagnostics()`.

### Stack and wiring

```python
@dataclass(frozen=True)
class LspStack:
    ...
    pull: bool = True
    save: bool = False
    settle: float = 3.0
    quiescence: str | None = None   # "server_status" is the only value today
```

The Rust default becomes:

```python
LspStack(
    name="rust",
    markers=("**/Cargo.toml",),
    command=("rust-analyzer",),
    languages=("rust",),
    extensions=(".rs",),
    pull=False,
    save=True,
    settle=15.0,
    quiescence="server_status",
)
```

`LspManager.get_or_start` passes `quiescence=stack.quiescence` into `LspServer`.
`lsp_servers_json` overrides can set the same field; an unknown value falls back
to `None` (settle behavior).

### Tracker

`quiescence="server_status"` instantiates one tracker per `LspServer`:

```python
class ServerStatusTracker:
    health: str | None = None
    quiescent: bool | None = None
    seq: int = 0          # increments on every status notification
    busy_seq: int = 0     # increments when a status reports quiescent == False
    waiters: set[asyncio.Event] = field(default_factory=set)

    def client_capabilities(self) -> dict:
        return {"experimental": {"serverStatusNotification": True}}

    def handle(self, params: dict) -> None:
        self.health = params.get("health")
        self.quiescent = bool(params.get("quiescent"))
        self.seq += 1
        if self.quiescent is False:
            self.busy_seq += 1
        logger.debug("lsp server status health={} quiescent={}",
                     self.health, self.quiescent)
        if self.health not in (None, "ok"):
            logger.warning("lsp server health={} message={}",
                           self.health, params.get("message"))
        for waiter in self.waiters:
            waiter.set()
```

`LspServer` merges the tracker's capabilities into the `initialize` payload and
delegates the `experimental/serverStatus` notification to it. All other unknown
notifications remain dropped.

### Readiness wait

`publishDiagnostics` continues to populate `_diagnostics` and now also bumps a
**per-path** publish counter (`_publish_counts[path]`), so a publish for one file
cannot satisfy a wait for another.

`diagnostics(path)` keeps the pull path unchanged. For push mode with a
tracker:

1. Compute `grace = min(self.diagnostics_timeout, self.settle)`.
2. If `tracker.seq == 0` at call start, run the existing settle loop unchanged
   (extracted as `_settle_wait` with no behavior change).
3. Otherwise register one `asyncio.Event` in both
   `_diagnostic_events[target]` and `tracker.waiters`, and loop until the
   deadline:
   - `busy_seq_at_start = tracker.busy_seq` and
     `publish_at_start = self._publish_counts.get(target, 0)`.
   - Done when `tracker.quiescent is True` **and**
     (`self._publish_counts.get(target, 0) > publish_at_start` **or**
     `tracker.busy_seq > busy_seq_at_start`).
   - On deadline, return the latest cached diagnostics (normally `[]`).
4. In `finally`, remove the event from both registries.

Requiring publish progress or an observed busy phase (rather than a bare
`quiescent:true`) avoids returning an empty list on a stale `quiescent:true`
that was already true before the write. Tracking `busy_seq` in the tracker (not
sampling `quiescent` on wake) handles a `false → publish → true` sequence that
arrives in one read batch. Clean writes still return fast because
rust-analyzer either publishes an empty list or briefly toggles to
`quiescent:false` before returning to `true`.

Pseudo-code:

```python
grace = min(self.diagnostics_timeout, self.settle)
tracker = self._tracker
if tracker is None or tracker.seq == 0:
    return await self._settle_wait(target, grace)

busy_seq_at_start = tracker.busy_seq
publish_at_start = self._publish_counts.get(target, 0)
event = asyncio.Event()
self._diagnostic_events[target] = event
tracker.waiters.add(event)
deadline = loop.time() + grace
try:
    while True:
        settled = (
            tracker.quiescent is True
            and (
                self._publish_counts.get(target, 0) > publish_at_start
                or tracker.busy_seq > busy_seq_at_start
            )
        )
        if settled:
            return self._diagnostics.get(target, [])
        remaining = deadline - loop.time()
        if remaining <= 0:
            return self._diagnostics.get(target, [])
        event.clear()
        # nothing between clear() and wait() can be missed: no await in between
        try:
            await asyncio.wait_for(event.wait(), remaining)
        except TimeoutError:
            return self._diagnostics.get(target, [])
finally:
    self._diagnostic_events.pop(target, None)
    tracker.waiters.discard(event)
```

Note: the loop re-evaluates the `settled` condition on every wake, so a status
toggle and a publish that arrive in the same read batch are both observed. The
`busy_seq` counter (not a sampled boolean) preserves a `quiescent:false →
publish → quiescent:true` sequence even when it is processed between waits.

## Fallback

- `quiescence=None` → existing settle loop, unchanged.
- `quiescence="server_status"` but no status has ever been seen
  (`tracker.seq == 0`) → existing settle loop.
- Status seen, but neither a publish nor a busy phase occurs before the deadline
  → return the latest cached value (normally `[]`). This is the rare
  no-toggle/no-publish clean case.

The fallback grace remains `min(diagnostics_timeout, settle)`, so the worst-case
bound is unchanged (5 s by default, 15 s only when `lsp_diagnostics_timeout`
is raised to at least 15).

## Configuration

No new settings. The behavior is controlled by the per-stack `quiescence`
field, settable through `lsp_servers_json`. Existing settings (`lsp_enabled`,
`lsp_initialize_timeout`, `lsp_diagnostics_timeout`,
`lsp_failure_backoff_seconds`) are unchanged.

## Health and logging

Status notifications are debug-logged. `health` values other than `ok` are
logged at warning level with the optional message. Health is not surfaced in the
About API or UI in this cycle.

## Testing

### Fake LSP server (`tests/fake_lsp_server.py`)

Add a `--server-status` mode:
- inspect the `initialize` capabilities and only emit status when
  `experimental.serverStatusNotification` was advertised (also asserting the
  capability);
- emit an initial `{health: "ok", quiescent: true}` after `initialized`;
- on `didSave`, emit `{quiescent: false}` → optional publish → `{quiescent:
  true}`.

Sub-modes:
- clean: no diagnostics (or an empty publish) → fast empty return;
- error: publish an error → diagnostics returned;
- stale-true: `quiescent` already true, publish an error → fast-path diagnostics;
- stuck-busy: `quiescent:false` never becomes true → deadline returns latest;
- no-status: existing `--push` behavior → settle fallback.

### Unit tests (`tests/test_lsp_client.py`)

- `initialize` capabilities include `experimental.serverStatusNotification`
  when `quiescence="server_status"`.
- A clean write returns well under `grace` with no diagnostics.
- An erroneous write returns the diagnostic.
- A publish while quiescent returns immediately.
- A busy status keeps waiting until quiescent.
- A server without status notifications uses the settle fallback.

### Real server (`tests/test_lsp_real.py`)

- Warm up (one write) so initialization/loading is not measured, then time a
  clean edit with `diagnostics_timeout=10` and assert `< 2 s` and no
  diagnostics.
- An erroneous edit still returns a diagnostic.
- Availability-skipped when `rust-analyzer`/`cargo` are absent.

Existing pull and settle tests remain unchanged.

## Out of scope / limits

- Flycheck-only (cargo/borrow-check) diagnostics that arrive after quiescence
  are not awaited; they may be missed on that write.
- Relies on rust-analyzer publishing around quiescence; the stale-true guard
  and settle fallback mitigate ordering issues.
- `server_status` is rust-analyzer-specific. Future stacks (e.g. gopls) need a
  new `quiescence` value and tracker, not a change to the wait loop.
- No About/UI surface for server health.
- No change to which tools trigger diagnostics (`write_file`, `append_file`,
  `edit_file` only).

## Roadmap impact

- On completion, move D19 from the deferred backlog into sub-project history
  (#36) and mark it DONE.
- Add a pointer from the original LSP diagnostics design
  (`2026-11-19-lsp-diagnostics-design.md`, Rust note) to this spec.

## References

- rust-analyzer LSP extensions — Server Status: experimental client capability
  `{ "serverStatusNotification": boolean }`, notification
  `experimental/serverStatus` with `{health, quiescent, message?}`.
- Existing implementation: `packages/agentbox-harness/src/agentbox_harness/lsp/`
  (`stacks.py`, `client.py`, `manager.py`, `hooks.py`).
