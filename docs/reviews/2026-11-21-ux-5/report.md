# Agentbox live UX review - 2026-11-21 (UX-5)

**Scope:** A live end-to-end review of the web UI against a real backend and a real DeepSeek
provider. Every screenshot in this folder was captured from the running app (not Storybook).
The review focused on visual glitches, poor renderings, real chat usability, and harness
efficiency.

## Environment reviewed

- Backend: `uv run python -m agentbox_api.dev_server` on `http://127.0.0.1:8000`
- Frontend: Vite dev server on `http://localhost:5173`
- Database: temporary `agentbox-review.db` (removed after the review)
- Provider: DeepSeek (`kind=deepseek`, base `https://api.deepseek.com/v1`) with a real API key,
  models `deepseek-flash` and `deepseek-v4-pro`
- Agent: `Reviewer` on `deepseek-v4-pro` with the first-run read-only filesystem tools
- Browser: Playwright-driven Microsoft Edge
- Viewports: 1440x900, 1920x1080, 390x844
- Themes: light and dark
- LSP was disabled during this pass so chat/layout results were not mixed with language-server
  startup latency.

The provider key was entered through the provider form, stored only in the temporary review
database, and never committed. The temporary database and run logs were deleted after the
review. No key appears in this report or in any screenshot.

## Method

1. Completed the real first-run wizard: provider test, provider creation, agent creation,
   project + session creation.
2. Ran real DeepSeek turns: tool use, Markdown/table/code, a 400-word guide, a 1200-word essay
   (stopped mid-run), an authentication failure, retry after recovery, and Mermaid generation.
3. Used the built-in `test_markdown` provider fixture for a deterministic valid + invalid
   Mermaid case.
4. Measured the live AG-UI stream directly over HTTP (first byte, total time, event order).
5. Captured every page at desktop, wide, mobile, light, and dark; inspected console and network
   failures at each step.

## Severity model

- **P0 - Blocker:** unusable or corrupts state.
- **P1 - High:** common flow is broken or a headline visual is unusable.
- **P2 - Medium:** significant usability/polish problem with a workaround.
- **P3 - Low:** cosmetic, consistency, or minor accessibility issue.

## What worked

These flows were exercised successfully and should not regress:

- Live DeepSeek streaming with ordered reasoning, text, and tool events.
- Markdown headings, paragraphs, lists, tables, and syntax-highlighted code with copy controls
  ([14](assets/14-chat-bottom.png), [15](assets/15-chat-dark-bottom.png)).
- Real tool use: `list_directory` ran and the answer summarized the project root.
- Stop/cancel mid-run: the partial answer persisted with a `cancelled` chip and Retry
  ([18](assets/18-chat-stopped.png)).
- Provider failure is no longer silent: a 401 produced a per-turn error card with Retry
  ([31](assets/31-provider-auth-error.png)), and retry after restoring the key recovered without
  duplicating the user turn ([32](assets/32-retry-recovered.png)).
- Provider presets, connection test with latency and sample models ([04](assets/04-provider-test.png)),
  and model discovery.
- First-run wizard completed provider -> agent -> project/session and updated the checklist 0/4
  to 4/4.
- Desktop shell, agent list, provider list/models tab, skills, admin, and API keys pages render
  cleanly in dark mode ([19](assets/19-agents.png), [20](assets/20-providers.png),
  [37](assets/37-skills.png), [38](assets/38-admin.png), [39](assets/39-apikeys.png)).
- Wide layout stays centered and does not stretch forms edge-to-edge
  ([26](assets/26-wide-home.png), [29](assets/29-provider-edit-wide.png)).
- Invalid Mermaid falls back safely with the source and a copy action and no longer corrupts
  the page ([36](assets/36-fixture-mermaid.png)). The former global "Syntax error" leak did not
  reproduce.

## Remediation verification (waves 1-2)

Wave 1 fixed and verified **UX-5.1 through UX-5.5** (L1 and L2 in this report):

- [post-fix empty session](assets/post-fix-01-empty-session.png) - composer pinned at the bottom.
- [post-fix long answer](assets/post-fix-02-long-answer.png) - a real 500-word DeepSeek answer;
  the messages pane scrolls to the bottom and the composer stays visible
  (`composerBottom=876` of a 900px viewport; messages `clientHeight=685`, `scrollHeight=2449`).
- [post-fix follow-up](assets/post-fix-03-new-turn-in-view.png) - the new question and its answer
  are visible together; the previous answer ends above the new question.
- [post-fix wide Mermaid](assets/post-fix-04-mermaid.png) and
  [diagram crop](assets/post-fix-05-mermaid-block.png) - a real DeepSeek `flowchart LR` renders at
  `1026px` inside a `1052px` block with legible labels.
- Mobile (390x844), MCP split view, and jump-to-latest are covered by the new Playwright tests.

The wave-1 code review also found and fixed four follow-ups that the original screenshots had not
exercised: the MCP split view can clip the composer with long content (split now uses a constrained
row and a flex chat column), long project/session lists were clipped by the fixed shell (the pane
now scrolls), the Mermaid rule over-upscaled tall/small diagrams (the `max-width` override was
removed and a vertical-diagram test was added), and the original follow-up e2e was a false positive
(it now waits for turn 2 to persist).

Wave 2 closed all remaining tracked items:

- Mermaid zoom/pan/reset controls, a copy-source action, and a browser Fullscreen API toggle that
  keeps the same toolbar and pan/zoom behavior.
- Consistent friendly labels for untitled sessions across Home, the project tree, and the header.
- Onboarding is gated on loaded setup data, has a readable active-step row, and navigates straight
  into the created session.
- Mobile navigation wraps instead of hiding API keys and Admin.
- Provider status is `configured` until a successful connection test, then `verified`; the table
  has a Test connection action.
- Persisted activity now includes reasoning text and tool input/output previews.
- `<1ms` durations, friendly provider-auth errors with raw details, form placeholders/alignment,
  API-key input form semantics, mono numerals, inline Copy Markdown, readable prose measure,
  empty-session guidance, compact setup checklist, `Project root` path label, favicon, avatar-404
  removal, empty streaming code fences, live reasoning opened while streaming, context-token usage,
  error-route scrolling, shared session route constant, instant auto-follow, rail sizing, optimistic
  user messages, and shared e2e login/setup helpers.

All **UX-5** items are now closed in [`docs/ROADMAP.md`](../../ROADMAP.md), including the e2e
login/setup helper deduplication (UX-5.41).

Wave-2 live evidence with the real DeepSeek provider:

- [Home after setup](assets/post-fix-06-home.png) - compact setup card, consistent `Untitled
  session` label, and `Project root` instead of a stray `.`.
- [Provider configured](assets/post-fix-07-provider-status.png) and
  [Provider verified](assets/post-fix-08-provider-verified.png) - the row is `CONFIGURED` until
  Test connection succeeds (`2 models in 350ms`), then `VERIFIED`.
- [Empty session guidance](assets/post-fix-09-empty-session-guidance.png).
- [Token usage](assets/post-fix-10-token-usage.png) - `2.2k tokens` in the session header after a
  completed turn (`2.3k` after the next turn).
- [Activity details](assets/post-fix-11-activity-details.png) - persisted reasoning text is
  available after the run.
- [Mermaid tools](assets/post-fix-12-mermaid-tools.png) - zoom in/out, reset, copy diagram, and a
  legible horizontal flow.
- [Mobile navigation](assets/post-fix-13-mobile-nav.png) - two wrapped rows; `scrollWidth=390`,
  `clientWidth=390`, and all six destinations visible.

Verification run after the fixes:

- Vitest: 75 files / 184 tests passed.
- Playwright: 37 tests passed, including mobile nav, split view, follow-up, jump-to-latest, wide +
  vertical Mermaid, fullscreen enter/exit, and onboarding navigation.
- `uv run pytest packages/agentbox-api -q`: 179 passed.
- `uv run pytest packages/agentbox-providers -q`: 18 passed.
- `bun run build`, `uv run ruff check packages`, `uv run ty check packages`: passed.
- The live verification used the real provider key through the process environment only; the
  temporary database and logs were removed and no key was committed.

## Findings

### L1. The chat session does not fill the viewport; the composer scrolls away and auto-scroll never engages - **P1**

**Status (wave 1):** Fixed and verified. See [Remediation verification](#remediation-verification-wave-1).

**Evidence:** [08](assets/08-session-empty.png), [10](assets/10-chat-streaming.png),
[13](assets/13-chat-long-finished.png), [17](assets/17-chat-running.png),
[24](assets/24-mobile-session.png), [27](assets/27-wide-session.png)

This is the most damaging live issue and it contradicts the UX-2 "sticky composer / scrollable
message pane" result. The session page is a normal document that scrolls with the page:

- On an empty session at 1440x900, `main` is 900px tall but the session wrapper (`.fullBleed`)
  is only 195px. The message pane (`.messages`) is 28px tall; the composer sits directly under
  the header at `top=103`. The remaining ~700px is empty canvas ([08](assets/08-session-empty.png)).
- After one answer, the document is 1220px tall and the composer is at `top=1068`, i.e. 168px
  below a 900px viewport ([10](assets/10-chat-streaming.png)).
- Sending a new long prompt appended 1600px of content, but `window.scrollY` stayed at 320 and
  the new user turn appeared below the fold ([12](assets/12-chat-long-running.png)). The stream
  then rendered out of view ([17](assets/17-chat-running.png)).
- The "Jump to latest" control never appears because it is driven by scroll state on
  `.messages`, which never scrolls.
- On mobile the effect is worse: after reading an answer the user must scroll the entire
  document to reach the composer ([24](assets/24-mobile-session.png)).

**Turn-boundary confusion (reported from [13](assets/13-chat-long-finished.png)):** after
sending the second prompt, the visible region shows the tail of the *first* answer (table, code,
activity) followed by `YOU / Write a detailed 400-word...`, while the answer to that second
prompt is below the fold. To a reader this reads as if the question sits beneath its own answer
or as if the previous answer is answering the next question. The persisted order is **not** the
cause: the API rebuilds the parent chain root-to-leaf
(`packages/agentbox-api/src/agentbox_api/routers/sessions.py`, `list_messages`), and the live DOM
was verified as `user1, assistant1, user2, assistant2`. The cause is that sending a message does
not scroll to or anchor the new user turn, so the viewport remains at the old bottom boundary and
the new Q/A pair renders below it. The new question is also not brought into view while its
answer streams ([12](assets/12-chat-long-running.png), [17](assets/17-chat-running.png)).

**Expected:** on send, scroll so the new user message is visible (the previous answer should end
above it), then follow the live answer. This would remove the misleading "answer above the
question" framing in [13](assets/13-chat-long-finished.png).

**Measured**

| State | Value |
|---|---|
| `main` client height | 900px |
| `.fullBleed` height, empty session | 195px |
| `.messages` height, empty session | 28px |
| Composer top after one turn | 1068px (viewport 900px) |
| Document height during long run | 2844px |
| `window.scrollY` before/after new streamed content | 320 / 320 |

**Root cause:** `apps/web/src/design-system/shell/shell.module.css:1` uses a grid with
`min-height: 100vh` and an auto row, and `.workspace` (`:15`) is the page scroll container.
`PageContainer`'s `fullBleed` class (`:27`) has no height, so `apps/web/src/pages/session.module.css`
`.session { height: 100% }` resolves against a content-sized parent. `useAutoScroll`
(`apps/web/src/chat/useAutoScroll.ts`) then scrolls a `.messages` element that has no overflow.

**Expected:** a fixed-height shell, a message pane that scrolls independently between header
and composer, an always-visible composer, auto-scroll while the user is at the bottom, and a
jump-to-latest affordance when they are not.

**Regression risk:** this is exactly the kind of integration-level layout bug that Storybook
screenshots cannot catch. Add a Playwright assertion that the composer is inside the viewport
after a long answer and that the message pane is the scroll container.

### L2. Horizontal Mermaid diagrams render as unreadable thumbnails - **P1**

**Status (wave 1):** Fixed and verified. See [Remediation verification](#remediation-verification-wave-1).

**Evidence:** [33](assets/33-mermaid-valid.png), [34](assets/34-mermaid-block-crop.png)

A real DeepSeek Mermaid flowchart (five nodes in a horizontal chain) rendered as a 300x26
thumbnail inside a 1052px-wide block. Node labels are roughly 3px tall and cannot be read.

**Measured DOM**

- `.mermaid-block` content box: 1052 x 52
- `.mermaid-canvas`: 300 x 26
- SVG: `width="100%"`, `viewBox="4 4 936 82.25"`, `style="max-width: 936px"`
- Computed SVG size: 299.95 x 26.34

**Root cause:** Mermaid emits `width="100%"`; `.mermaid-canvas`
(`apps/web/src/chat/markdown.css:245`) is a shrink-wrapped flex item with `min-width: min-content`.
The percentage width resolves against the default ~300px replaced-element width, so a wide
diagram is scaled down instead of filling the block.

**Expected:** diagrams scale up to the available width (and only shrink for very large graphs),
with a sensible minimum text size.

### L3. Rendered Mermaid diagrams have no visible zoom/pan or source-copy affordance - **P2**

**Evidence:** [34](assets/34-mermaid-block-crop.png), [36](assets/36-fixture-mermaid.png)

`MermaidBlock` wraps the SVG in `react-zoom-pan-pinch` but renders no controls or hint. There is
also no "copy source" action for a successfully rendered diagram, although the fallback has
"Copy diagram". The README promises "Mermaid diagrams with pan/zoom and source copy"; a user
cannot discover either on a rendered diagram.

### L4. Untitled sessions expose internal ids, and labels are inconsistent - **P2**

**Evidence:** [07](assets/07-new-session.png), [08](assets/08-session-empty.png)

Immediately after the wizard created a session:

- Home "Recent sessions" shows the project's agent id as the title:
  `08c3c7d025a5408791113b7e2ef74c36` ([07](assets/07-new-session.png)).
- The sidebar shows `Session 1`; the session header shows `Session`.
- After the first message the title becomes the prompt prefix everywhere.

**Root cause:** `apps/web/src/pages/HomePage.tsx:186` falls back to `session.agent_id` when
`title` is empty. The sidebar and header use different fallbacks.

**Expected:** a friendly, consistent placeholder (for example "New session") on Home, in the
project tree, and in the header until the session is titled.

### L5. The onboarding wizard reappears on a configured instance and its step row is hard to read - **P2**

**Evidence:** [25](assets/25-mobile-onboarding.png), [07](assets/07-new-session.png)

With one provider, two agents, and `4 of 4 complete` visible behind it, the wizard opened again
as soon as local storage was cleared. On any new browser/incognito session it would therefore
ask an already-configured user to connect a provider again.

**Root cause:** `apps/web/src/pages/HomePage.tsx:70` opens the wizard from a snapshot that is
still loading (providers=0, agents=0) and never closes it when the real counts arrive. The only
gate is a `localStorage` dismissal flag (`apps/web/src/onboarding/useOnboardingPreference.ts`).

Also, the step labels (`Welcome Provider Agent Session Done`) are all identical weight with no
separators or active/complete state; on mobile they read as one run-on sentence.

### L6. "Create project and start session" does not open the session - **P2**

**Evidence:** [07](assets/07-new-session.png)

The wizard creates the session but leaves the user on a "Setup complete" dialog over Home. The
only way to reach the new session is to find it in the project tree or the recent list. A
"Open session" primary action (or direct navigation) is expected from a button with that label.

### L7. Mobile navigation hides two destinations with no affordance - **P2**

**Evidence:** [23](assets/23-mobile-home.png), [24](assets/24-mobile-session.png)

At 390px the nav renders Home, Agents, Providers, and part of Skills. `API keys` and `Admin`
are off-screen. Measured `scrollWidth=594` vs `clientWidth=390`; `overflow-x: auto` works, but
there is no fade, scrollbar, or "more" affordance indicating that more destinations exist
(`apps/web/src/design-system/navigation/navigation.module.css:124`).

### L8. Reasoning content and tool arguments/results disappear after a run - **P2**

**Evidence:** [11](assets/11-activity-expanded.png)

During streaming, reasoning and tool segments are visible. After the run, the expanded
`Activity` block only shows:

- `Reasoning done 406ms` (no reasoning text)
- `list_directory success 0ms` (no arguments or result)

The backend collector stores only `reasoning_ms` and tool name/status/duration
(`packages/agentbox-api/src/agentbox_api/activity.py`), so the actual reasoning and tool I/O are
discarded. This conflicts with the README's "visible reasoning and tool traces" and with the
UX-2 roadmap wording.

A related polish detail: sub-millisecond tools display `0ms`; `<1ms` would be clearer.

### L9. Provider authentication errors are functionally correct but expose a raw payload - **P3**

**Evidence:** [31](assets/31-provider-auth-error.png), [32](assets/32-retry-recovered.png)

The error card now appears on the failed turn, with an `ERROR` chip and Retry, and retry after
restoring the key succeeds. However, the message is the raw runtime string:

```
status_code: 401, model_name: deepseek-v4-pro, body: {'message': 'Authentication Fails, Your
api key: ****alid is invalid (request_id: ...)', 'type': 'authentication_error', ...}
```

**Expected:** a short human summary ("Provider authentication failed. Check the API key in
Providers.") with the raw payload behind "Details", plus a link to the provider.

### L10. Empty form fields and a misaligned model form - **P3**

**Evidence:** [21](assets/21-models.png), [37](assets/37-skills.png),
[38](assets/38-admin.png), [40](assets/40-agent-create.png)

- On Providers -> Models, the `CONTEXT WINDOW` label sits ~40px higher than `PROVIDER` and
  `MODEL NAME` because its helper text participates in the grid row. The Provider, Model name,
  and Filter by label controls render as blank dark slabs with no placeholder ([21](assets/21-models.png)).
- Skills and Admin create forms have the same empty-slab inputs with no placeholders or examples
  ([37](assets/37-skills.png), [38](assets/38-admin.png)).
- The agent drawer is otherwise well structured, but its name/model inputs are also blank
  ([40](assets/40-agent-create.png)).

**Expected:** placeholders that show format examples (`e.g. deepseek-v4-pro`, `review changes
for security`) and baseline-aligned labels.

### L11. Pixel font makes `0` read as `8` in numeric badges - **P3**

**Evidence:** [39](assets/39-apikeys.png)

The scope badge visually reads `8 SELECTED`; DOM verification confirmed the text is
`0 selected` (15 checkboxes, 0 checked). The Silkscreen zero is ambiguous at badge size. The
Home stat `0` has the same issue. Use the mono font for numerals or a slashed/zero-dot glyph.

### L12. Smaller visual and consistency issues - **P3**

- `Copy Markdown` sits on its own right-aligned row far from the `REVIEWER` label, then the
  answer starts with another gap ([10](assets/10-chat-streaming.png), [16](assets/16-chat-dark-top.png)).
- At 1920px chat text runs the full ~1540px content width; a readable measure (~75ch) would be
  better for prose, keeping tables/code full width ([27](assets/27-wide-session.png)).
- An empty session has no guidance at all, only a blank canvas and a top composer ([08](assets/08-session-empty.png)).
- The completed setup checklist occupies a large Home block forever with a `setup complete` pill
  ([22](assets/22-home-dark.png)); it should collapse or be dismissible.
- The project path `.` renders as a stray dot on the right of the Home projects card
  ([22](assets/22-home-dark.png)); show the resolved path or omit it.
- No favicon: every page logs `404 /favicon.ico`.
- Every session load fires `404 /api/agents/Agent/avatar?v=0` before session data arrives
  (`SessionPage.tsx:202` fallback name `Agent`); the real avatar then loads correctly.
- Password/API-key inputs are not inside a `<form>` (Chromium warning), so Enter does not submit
  and password managers cannot associate the field.
- While streaming, an incomplete code fence briefly renders empty code chrome
  ([17](assets/17-chat-running.png)).

### L13. Provider status shows READY while the live key is invalid - **P2**

**Evidence:** [20](assets/20-providers.png), [31](assets/31-provider-auth-error.png)

After the stored key was replaced with an invalid one and a real run failed with HTTP 401, the
Providers page still showed the green `READY` pill. The status is derived from stored model rows,
not from a connectivity check, so it reassures the user precisely when the provider is unusable.
`READY` should mean "verified reachable" or the UI should show the last test result/failure and
re-test after key changes.

### L14. Token/context usage is stored but never surfaced - **P3**

**Evidence:** harness measurement and `turnrow.context_tokens` values in the review database
(3240, 3847, 5614, 5771, 5970, 5788 for successful turns)

The backend records context token usage on every successful assistant turn, but no page shows
it. A per-session context/usage indicator would make the cost of long turns observable and help
users decide when to fork or start a new session.

### L15. Live reasoning is collapsed by default - **P3**

**Evidence:** [10](assets/10-chat-streaming.png), [17](assets/17-chat-running.png)

While a run streams, reasoning is rendered inside a collapsed `<details>` whose summary is just
"Thinking."; the run strip shows elapsed time but the reasoning text is hidden unless the user
opens it. Combined with L8 (the content is dropped after the run), reasoning is effectively
invisible in normal use.

## Harness efficiency

Measured directly against the running backend with a streaming HTTP client, not inferred from
the UI:

| Measurement | Value |
|---|---|
| Short prompt ("Reply with the single word OK") | 0.276s to first byte and first AG-UI event |
| Total turn time | 1.588s |
| Payload | 3101 bytes, 22 events |
| Event order | `RUN_STARTED -> REASONING_START -> REASONING_MESSAGE_CONTENT* -> REASONING_MESSAGE_END -> TEXT_MESSAGE_* -> RUN_FINISHED` |
| Duplicate/out-of-order events | none observed |

- A real 400-word Markdown answer streamed without stalls; a 1200-word answer was stopped mid-run
  at ~8s and the partial content persisted correctly.
- Stop and retry are both real and work server-side: the cancelled turn is stored with status
  `cancelled`; retry after a 401 replaced the error turn without duplicating the user turn.
- Token usage is already persisted (`turnrow.context_tokens`: 3240, 3847, 5614, 5771, 5970,
  5788 for successful turns) but is not surfaced anywhere in the UI. A small context/usage
  indicator per session would make the cost of long turns observable.
- The only obvious request waste is the fallback `Agent` avatar 404 on each session load.

Overall the streaming harness is fast and correct in this local single-user configuration; the
largest efficiency loss in practice is that reasoning tokens are generated and streamed but
then discarded from the persisted trace.

## Reproduction notes

- Create the provider through the wizard with `kind=deepseek`, `https://api.deepseek.com/v1`,
  and the models URL; the preset fills both URLs and the test connection reports the two models.
- Use a prompt that produces a horizontal Mermaid chart (`graph LR`/`flowchart LR`, or a chain
  of five nodes) to reproduce L2; a vertical `graph TD` hides the width bug.
- Reproduce L1 by sending a 400+ word prompt and watching the composer leave the viewport; then
  send another prompt and observe that the view does not follow the stream. Screenshot
  [13](assets/13-chat-long-finished.png) shows the resulting boundary: the previous answer is
  above the new question while the new answer is below the fold (data order itself is correct).
- Reproduce L5 by clearing `agentbox-onboarding-v1` from local storage on an account that already
  has providers and agents, then reloading Home.
- Reproduce L11 by opening API keys with no scopes selected and reading the badge out loud.

## Recommended priority

> Wave 1 (L1/L2, roadmap UX-5.1 through UX-5.5) is complete and verified. The order below applies
> to the remaining findings.

### Fix first (P1)

1. **L1** - make the session shell viewport-bound, make `.messages` the scroll container, pin the
   composer, restore auto-scroll/jump-to-latest, and scroll/anchor the newly sent user turn so a
   question never appears beneath the previous answer.
2. **L2** - let Mermaid SVGs fill the block width with a legible minimum.

### Next (P2)

3. **L4** - friendly, consistent untitled-session labels.
4. **L5/L6** - gate the wizard on loaded setup state, fix the step row, and navigate straight into
   the new session.
5. **L7** - mobile nav overflow affordance or overflow menu.
6. **L8** - persist/display reasoning text and tool args/results (or stop claiming traces).
7. **L3** - add zoom controls and copy-source for rendered diagrams.
8. **L13** - make provider `READY` mean verified/reachable, or show the last test result.

### Later (P3)

9. **L9** - friendly provider error copy.
10. **L10** - form placeholders and Context window alignment.
11. **L11** - numeral legibility.
12. **L12** - cosmetic consistency batch (each item tracked separately in UX-5.20 through
    UX-5.28).
13. **L14** - surface context/token usage.
14. **L15** - make live reasoning visible by default.

### Suggested regression coverage

- Playwright: after a long answer, the composer is inside the viewport, `.messages` scrolls, and
  sending a message keeps the latest turn in view ([08/10/17] class of bug).
- Playwright: after sending a follow-up, the newest user turn is above its answer and both are in
  view; the previous answer must end above the new question (guards the
  [13](assets/13-chat-long-finished.png) framing).
- Playwright: a horizontal Mermaid chart's SVG width is >= 80% of its block width ([33/34] class
  of bug).
- Component/integration: Home fallback label for an untitled session must not be an id.

## Evidence index

| File | Shows |
|---|---|
| [01](assets/01-login.png) | Login, light theme |
| [02](assets/02-first-run.png) | First-run wizard over Home |
| [03](assets/03-onboarding-provider.png) | Provider form in wizard |
| [04](assets/04-provider-test.png) | Successful connection test |
| [05](assets/05-onboarding-agent.png), [06](assets/06-onboarding-session.png) | Agent and session steps |
| [07](assets/07-new-session.png) | Setup complete, raw agent id in Recent sessions |
| [08](assets/08-session-empty.png), [09](assets/09-session-empty-reload.png) | Collapsed session layout |
| [10](assets/10-chat-streaming.png) | First real Markdown answer, composer off-screen |
| [11](assets/11-activity-expanded.png) | Expanded activity without reasoning/tool content |
| [12](assets/12-chat-long-running.png), [13](assets/13-chat-long-finished.png) | Long turn, no auto-follow; 13 shows the previous answer above the new question |
| [14](assets/14-chat-bottom.png), [15](assets/15-chat-dark-bottom.png) | Markdown/table/code, light and dark |
| [16](assets/16-chat-dark-top.png) | Dark session header/answer |
| [17](assets/17-chat-running.png) | Live streaming, thinking/stop, incomplete code fence |
| [18](assets/18-chat-stopped.png) | Cancelled turn with Retry |
| [19](assets/19-agents.png), [20](assets/20-providers.png), [21](assets/21-models.png) | Agent/provider/models pages |
| [22](assets/22-home-dark.png) | Home dark, completed setup block, `.` path |
| [23](assets/23-mobile-home.png), [24](assets/24-mobile-session.png) | Mobile nav overflow and session |
| [25](assets/25-mobile-onboarding.png) | Wizard reappearing on configured instance |
| [26](assets/26-wide-home.png), [27](assets/27-wide-session.png) | 1920px layouts |
| [28](assets/28-icon-tooltip.png) | Icon tooltip present |
| [29](assets/29-provider-edit-wide.png) | Provider edit drawer at 1920px |
| [30](assets/30-provider-invalid-key.png) | Provider edit saved (no key shown) |
| [31](assets/31-provider-auth-error.png), [32](assets/32-retry-recovered.png) | 401 error card and successful retry |
| [33](assets/33-mermaid-valid.png), [34](assets/34-mermaid-block-crop.png) | Tiny Mermaid render |
| [35](assets/35-mermaid-invalid.png) | Attempted invalid input message |
| [36](assets/36-fixture-mermaid.png) | Deterministic valid + invalid Mermaid fallback |
| [37](assets/37-skills.png), [38](assets/38-admin.png), [39](assets/39-apikeys.png) | Secondary pages |
| [40](assets/40-agent-create.png) | Agent create drawer |

## Limitations

- A single local user with the seeded admin account; no multi-user concurrency tests.
- LSP was disabled in this pass, so LSP diagnostics/quiescence UX was not evaluated.
- Mobile testing used a resized desktop browser, not a physical device; touch-specific gestures
  were not exercised.
- The invalid-Mermaid check used the built-in `test_markdown` fixture because quoting a literal
  triple-backtick fence through the automation shell was unreliable; the fallback path itself
  was still exercised in the real app.
