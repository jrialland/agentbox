# UX-2 — Chat Surface and Runtime UX

- **Date:** 2026-11-21
- **Status:** Draft (design approved; pending spec review)
- **Sub-project:** UX-2 — the chat surface, live run feedback, ordered reasoning/tool traces, Markdown/Mermaid rendering, composer, cancellation/retry, attachment history, and MCP App split view.
- **Source:** [`docs/reviews/2026-11-20-ux-review/report.md`](../../reviews/2026-11-20-ux-review/report.md) findings A1–A12.
- **Roadmap:** `UX-2` in [`docs/ROADMAP.md`](../../ROADMAP.md).
- **Reference client:** `jrialland/minimal-agent-example` AG-UI event handling (create containers on `*_START`, update by id, append in event order).

## 1. Context and scope

The chat works end-to-end, but the UX review found that it is hard to read and unreliable under real streaming: Markdown is unstyled, Mermaid renders partial source and corrupts the SPA, reasoning/tool activity disappears after completion, there is no run status or stop control, provider failures are silent, attachments vanish from history, edit/fork mode is invisible, and the composer is text-button-heavy.

UX-2 rebuilds the chat as a first-class surface and adds the backend support needed for persistence, cancellation, errors, and attachment download.

### 1.1 In scope

- Ordered AG-UI segment model for reasoning, tool calls, text, and MCP app attachments.
- Persisted summary activity on assistant turns and attachment metadata on user turns.
- Per-turn cancellation, stop button, partial-output preservation, and retry.
- AG-UI `RUN_ERROR` emission and per-turn error cards.
- Attachment download endpoint and history chips.
- Markdown stylesheet, highlight.js code rendering, copy controls.
- Safe Mermaid rendering only after complete fences, with compact fallback.
- Auto-scroll with “jump to latest”, sticky composer, running status strip.
- Composer redesign: icons, Enter to send, Send/Stop toggle, Ask/Agent segmented control, drag-and-drop attachments, mic icon, styled `/` and `@` menus.
- Edit/fork banner and cancellation.
- Resizable MCP App split view on desktop; mobile sheet.
- Removal of `legacy-chat.css`, the Bulma import, and the `bulma` dependency.
- End-of-cycle visual screenshot pack.

### 1.2 Out of scope

- A2A structured card editor and contextual help (UX-3).
- Validation, destructive confirmations, API error propagation outside chat, 404/session states (UX-4).
- New agent/model capabilities.
- Full event-log persistence (summary-only was chosen).

### 1.3 Dependencies

- UX-1 design system and `CommandShell`.
- Existing harness `Run.cancel()` / `CancellationToken`, AG-UI client, MCP Apps relay.

## 2. Goals and success criteria

- A completed answer is readable: Markdown hierarchy, lists, tables, highlighted code, copyable blocks.
- Mermaid diagrams render correctly after streaming; invalid diagrams degrade to a compact fallback; no leaked DOM nodes.
- Reasoning and tool activity appear in the true event order while running; persisted history shows compact activity chips.
- The user always knows when the agent is running and can stop it; partial output is kept.
- Provider/runtime failures are visible per turn and retryable.
- Attachments are visible in history and downloadable.
- The composer is reachable at all times, icon-first, and keyboard-friendly.
- MCP apps share the screen with chat on desktop and work on mobile.
- UX-2 ends with a screenshot pack that a reviewer can open without running the app.

## 3. Decisions and rationale

| # | Decision | Rationale |
|---|---|---|
| D1 | **Ordered segment reducer** keyed by AG-UI message/tool ids. | Preserves real interleaving; avoids the current single-buffer ordering bug. |
| D2 | **Summary-only persistence** for activity: tool names, status, duration, reasoning duration. | Chosen storage/scope trade-off; keeps history useful without storing full args/results/reasoning text. |
| D3 | **Attachment metadata persisted on user turns**. | Filenames/types are small and make history meaningful. |
| D4 | **Cancel endpoint + active-run registry**. | `Run.cancel()` exists; the API needs to expose it safely. |
| D5 | **Persist partial assistant output on cancel**, status `cancelled`. | User chose keeping partial work. |
| D6 | **Retry uses `retry_turn_id`** (no duplicate user turns). | Replaces the failed/cancelled branch cleanly. |
| D7 | **Per-turn error cards + manual Retry**, no auto-retry. | Predictable and avoids surprise loops. |
| D8 | **highlight.js** for code. | Lightweight, synchronous-enough, good enough for chat. |
| D9 | **Mermaid only on complete fences**, parse before render. | Fixes the SPA corruption found in the review. |
| D10 | **Simple spinner + Stop** for running state. | User choice; detailed activity is visible in segments/chips. |
| D11 | **Resizable split view** for MCP apps. | Preserves side-by-side context; mobile uses a sheet. |
| D12 | **Bulma removal** at the end of UX-2. | Chat becomes fully design-system native. |

## 4. Frontend architecture

### 4.1 Segment model

`apps/web/src/chat/segments.ts` owns the reducer and types.

```ts
type Segment =
  | { id: string; kind: "reasoning"; text: string; status: "streaming" | "done"; startedAt: number; endedAt?: number }
  | { id: string; kind: "tool"; toolCallId: string; name: string; args: string; result?: string; status: "running" | "success" | "error"; startedAt: number; endedAt?: number }
  | { id: string; kind: "text"; messageId: string; text: string; status: "streaming" | "done" }
  | { id: string; kind: "app"; messageId: string; tab: AppTab };
```

`useChat` keeps `segments`, `running`, `error`, `appTabs`, and `runStatus`, and dispatches AG-UI events through the reducer:

| Event | Action |
|---|---|
| `REASONING_MESSAGE_START` | append reasoning segment |
| `REASONING_MESSAGE_CONTENT` | append delta |
| `REASONING_MESSAGE_END` | mark done, record duration |
| `TOOL_CALL_START` | append tool segment |
| `TOOL_CALL_ARGS` | accumulate args |
| `TOOL_CALL_END` | mark args complete |
| `TOOL_CALL_RESULT` | set result, status, duration |
| `TEXT_MESSAGE_START` | append text segment |
| `TEXT_MESSAGE_CONTENT` | append delta |
| `TEXT_MESSAGE_END` | mark done |
| `ACTIVITY_SNAPSHOT` | append app segment linked to `toolCallId` |
| `RUN_ERROR` | mark turn error, stop running |
| `RUN_FINISHED` | stop running, finalize durations |

Unknown ids/events are ignored. Updates never reorder segments.

### 4.2 Components

- `SessionPage`: chat frame, history + live segments, sticky composer, fork banner, status strip, retry, app split.
- `MessageTurn`: user/assistant turn shell with role/avatar/timestamp/copy/attachments.
- `ActivityChips`: persisted summary chips (`Reasoning · 1.2s`, `3 tools · 4.1s`) with expandable tool rows.
- `ReasoningSegment`, `ToolSegment`, `TextSegment`, `AppSegment`: live segments.
- `MarkdownBlock`: styled ReactMarkdown + highlight.js + copy.
- `MermaidBlock`: complete-fence renderer with parse validation and fallback.
- `Composer`: icon-first composer and Send/Stop.
- `RunStatus`: spinner, “Thinking…”, elapsed, Stop.
- `ErrorCard`: message/code + Retry.
- `ChatSplit`: resizable chat/app panes; mobile sheet.

### 4.3 History mapping

Server messages provide `activity` and `attachments`. History renders:
- user text + attachment chips;
- assistant Markdown;
- activity chips if present;
- cancelled/error status chip and partial text if present.

Live segments are cleared after the run; persisted history takes over after refetch.

## 5. Backend design

### 5.1 Persistence

- `TurnRow.activity` (`JSON`, nullable) on assistant turns:
  ```json
  {
    "status": "success|cancelled|error",
    "reasoning_ms": 1200,
    "tools": [{"name": "read_text_file", "status": "success", "duration_ms": 420}],
    "error": {"code": "context_window", "message": "..."}
  }
  ```
- `TurnRow.attachments` (`JSON`, nullable) on user turns:
  ```json
  [{"id": "...", "filename": "note.txt", "media_type": "text/plain"}]
  ```
- Durations are measured **server-side** from run event timestamps; client timers are display-only and are never the source of the persisted summary.
- Alembic migration uses `batch_alter_table` for SQLite compatibility.
- `MessageRead` returns `activity` and `attachments`.

### 5.2 Cancellation

- Active-run registry keyed by session id, cleaned up on success/cancel/error.
- `POST /sessions/{sid}/messages/cancel`:
  - 202 + `{status: "cancelling"}` when a run is active;
  - 409 when no run is active.
- On cancel, `Run.cancel()` fires; the run finishes as `cancelled`.
- The finish path persists partial assistant text with status `cancelled` and activity summary.
- The frontend Stop button calls cancel, keeps partial text, shows cancelled status, and offers Retry.

### 5.3 Retry without duplicate user turns

- `POST /sessions/{sid}/messages` accepts optional `retry_turn_id`.
- If it points to an assistant turn, use its parent (user turn); if it points to a user turn, use it directly.
- Set `session.head_id` to that user turn and run with `record_user_turn=False`.
- The new assistant turn replaces the failed branch; no duplicate user message is stored.
- Frontend uses the failed/cancelled assistant turn id (or the user turn id if no assistant turn was stored).

### 5.4 Error events

- Normalize provider/runtime failures (auth, context window, network) into a `RunOutcome`.
- Streaming adapter emits an AG-UI `RUN_ERROR` with `code`/`message`.
- The frontend renders a per-turn `ErrorCard`; the backend persists an assistant turn with status `error` and error details when the run started.

### 5.5 Attachment download

- `GET /sessions/{sid}/attachments/{aid}` requires `sessions:read`, checks ownership/session, returns bytes with `Content-Type`, `Content-Disposition: inline; filename="..."`, and `Content-Length`.
- History attachment chips link to this endpoint with the auth token handled by the existing API client or an authenticated blob fetch.

## 6. Chat UX details

### 6.1 Layout and scrolling

- Session header: agent avatar/name, model/mode, About, optional branch indicator.
- Message pane scrolls internally; composer sticky.
- Auto-scroll only if near bottom; otherwise show “Jump to latest” with a new-activity pulse.
- Respect `prefers-reduced-motion`.

### 6.2 Markdown and code

- New design-system `.markdown-block` stylesheet: headings, paragraph spacing, lists, blockquotes, links, inline code, tables, horizontal rules.
- Code blocks: language label, highlight.js, copy button, contained horizontal scroll.
- Copy Markdown remains available but is a subtle icon action, not a prominent text button.

### 6.3 Mermaid

- While a `mermaid` fence is streaming, show “diagram building…” with the source in a code block.
- On fence completion, parse/validate, render off-DOM, then replace.
- On failure, show a compact error row with source and copy action; never render Mermaid’s error SVG into the page.
- Reset failure state on source change; cancel stale renders.
- Keep pan/zoom and copy-diagram controls.

### 6.4 Live activity

- Live segments render in event order.
- Reasoning: collapsed disclosure “Thinking…” while streaming, “Thought · 1.2s” when done.
- Tool: card with name, status, duration; expandable args/result.
- Text: Markdown segment.
- App: MCP app segment attached to its tool.
- Persisted history shows compact activity chips instead of full live segments.

### 6.5 Composer

- Icon-first toolbar with tooltips: paperclip, microphone, Ask/Agent segmented control, Send/Stop.
- Enter sends; Shift+Enter newline; empty input disables Send.
- Drag-and-drop and picker attachments; upload errors visible; chips removable.
- Slash-skill and `@`-file menus are styled popovers with keyboard navigation.
- Stop replaces Send while running.
- Running status strip: spinner + “Thinking…” + elapsed + Stop.

### 6.6 Edit/fork

- Edit shows a persistent banner above composer: “Editing from this turn — sending creates a new branch” with Cancel.
- History remains visible until send.
- After send, the transcript shows the new branch.

### 6.7 Errors and retry

- Per-turn error card with code/message and Retry.
- Retry uses `retry_turn_id` and same prompt/mode/skill/attachments where applicable.
- Focus moves to the error card after failure; user input is preserved.

### 6.8 Attachments

- Composer chips before send.
- User turn chips in history: filename + media type icon.
- Clicking a chip downloads/opens via the authenticated attachment endpoint.
- Image attachments may show a thumbnail in history; non-images show a file chip.

## 7. MCP App split view

- Desktop: chat and app tabs in a resizable split; divider keyboard-accessible; minimum widths.
- The app panel has its own scroll area and tab close buttons.
- Mobile: app tabs open as a full-screen sheet with a back/close action.
- Activity snapshot segments link the app to its tool call.

## 8. Testing

### 8.1 Backend

- Activity summary persisted for success, cancelled, and error runs.
- Attachment metadata persisted/returned.
- Cancel endpoint works and is idempotent; 409 when idle.
- `RUN_ERROR` emitted for normalized failures.
- Retry with `retry_turn_id` does not create a duplicate user turn.
- Attachment download auth/content type/disposition.
- Existing message/history/fork/compaction/MCP tests pass.

### 8.2 Frontend unit

- Reducer order tests: reasoning → tool → reasoning → text → tool → text; multiple text messages; unknown ids ignored; error/cancel finalization.
- Markdown headings/lists/tables/code.
- Mermaid complete-only render, stale render guard, fallback.
- Composer Enter/Shift+Enter/empty/Stop/attachments/slash/@ menus.
- Auto-scroll at bottom, stop when scrolled up, jump-to-latest.
- Fork banner behavior.
- Activity chips and error/retry.
- Attachment chips/download.

### 8.3 E2E

- Deterministic tool→text run: live tool card then final text in order.
- Cancel a slow run: partial text kept, cancelled status, Retry.
- Provider error: per-turn error card, Retry succeeds.
- Attachment upload → history chip → download.
- Markdown/table/code and Mermaid success/failure.
- MCP app split view and mobile sheet.
- Existing chat/avatar/MCP/A2A specs updated for new markup.
- Visual smoke for chat at 390/1280/1920, light/dark.

### 8.4 Screenshot deliverable

At the end of UX-2, produce `docs/reviews/2026-11-21-ux-2/` containing a short `README.md` and screenshots:

1. Empty chat with composer.
2. Markdown answer with headings, list, table, highlighted code.
3. Mermaid success.
4. Mermaid failure fallback.
5. Live reasoning → tool → text interleaving.
6. Persisted activity chips (collapsed and expanded).
7. Running state with spinner + Stop.
8. Cancelled turn with partial text + Retry.
9. Provider error + Retry.
10. Attachment history + download affordance.
11. Edit/fork banner.
12. MCP app split view on desktop.
13. Mobile chat + app sheet.
14. Light and dark variants for the core chat states.

Screenshots must use deterministic seeded data or the test provider, not live provider-dependent output. The README embeds them with one-line captions so the result can be reviewed quickly.

## 9. Acceptance criteria

- Markdown answers are readable and code is highlighted/copyable.
- Mermaid never corrupts the page; invalid diagrams show compact fallback.
- Live activity preserves true event order; history shows compact activity chips.
- Composer is always reachable, icon-first, Enter-to-send, Send/Stop.
- Auto-scroll follows only when at bottom; jump-to-latest is available.
- Stop keeps partial output; errors are per-turn with Retry; retry does not duplicate user messages.
- Attachments appear in history and download.
- MCP apps use resizable split desktop and sheet mobile.
- Bulma and `legacy-chat.css` are removed.
- Backend/frontend tests, build, Storybook, and E2E pass.
- Screenshot pack is committed and viewable.

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Segment ordering regressions | Reducer with id-keyed updates; interleaving unit tests. |
| Cancellation races | Idempotent registry cleanup; explicit 202/409 responses. |
| Mermaid async/stale renders | Source-keyed render; parse first; cleanup on source change. |
| Streaming re-renders | Localized segment state; avoid re-rendering full transcript per token where possible. |
| Summary loses detail | Compact chips + expandable names/status/durations; full detail remains in live run. |
| Retry duplicates turns | `retry_turn_id` + `record_user_turn=False`; backend test. |
| Screenshot flakiness | Deterministic test provider/seeded turns; stable viewport and animations disabled. |

## 11. Open items

- highlight.js theme will be a small custom token palette aligned with the design system (not a third-party theme).
- Image thumbnails in history use the existing media normalization limits; non-image attachments use file chips.
- The exact AG-UI error injection point will be settled during the implementation plan after checking `AGUIEventStream` capabilities.

## References

- UX review — [`docs/reviews/2026-11-20-ux-review/report.md`](../../reviews/2026-11-20-ux-review/report.md)
- UX-1 spec — `docs/superpowers/specs/2026-11-20-ux-1-design-system-design.md`
- AG-UI client reference — `jrialland/minimal-agent-example` `static/app.js`
- Roadmap — [`docs/ROADMAP.md`](../../ROADMAP.md)
