# Agentbox UX Review — 2026-11-20

**Scope:** Full manual review of the web UI and chat runtime using Playwright against a real backend and a real DeepSeek provider.

**Environment reviewed**

- Backend: `uv run python -m agentbox_api.dev_server`
- Frontend: `bun run dev` (Vite, `http://localhost:5173`)
- Database: temporary `review.db`, seeded with `admin` / `admin`
- Provider: DeepSeek (`deepseek` kind, models `deepseek-flash` and `deepseek-v4-pro`)
- Viewports: 1280×720, 1920×1080, 390×844, plus dark color scheme
- Screenshots: all evidence is in [`assets/`](assets/)

No API key is included in this report or in the committed screenshots. The temporary review database was removed after the review.

---

## Executive summary

The core plumbing works: login, provider/model setup, agent creation, real streaming chat, tool execution, attachments, file mentions, and session branching all function end-to-end. The problem is the experience around that plumbing. The product currently looks and behaves like a developer console rather than a polished agent workspace.

The most damaging problems are:

1. **Assistant Markdown is completely unstyled.** Headings, paragraphs, lists, tables, and code blocks all render with the same 16px/400-weight typography and zero vertical margins. This makes normal agent answers hard to read.
2. **Mermaid rendering during streaming breaks the entire SPA.** Partial Mermaid source is rendered on every token, failed renders inject huge “Syntax error in text” blocks into `document.body`, and those blocks persist when navigating to other pages. One normal “give me a diagram” request can make the app unusable until reload.
3. **Chat does not auto-scroll or keep the composer in reach.** After a long answer the viewport stays at the top; the user must manually scroll thousands of pixels to read the answer and then again to type.
4. **Provider/runtime failures can be completely silent.** An authentication failure from the model provider persisted the user message, produced no error in the UI, and left a dangling turn with no retry action.
5. **Several API failures are shown as success or as empty data.** A failed model refresh showed “Refreshed 0 models”; a 500 on `GET /projects` made the sidebar silently empty; a failed message refetch erased the visible conversation.
6. **Data validation is missing in user-facing flows.** Blank projects/providers can be created, non-existent project paths are accepted, and empty session/agent submissions give no feedback.
7. **Destructive actions are inconsistent.** Deleting a project/provider/agent is immediate; deleting a session asks for confirmation.
8. **Mobile and wide-screen layouts are not production-ready.** At 390px the nav stacks vertically and content overflows; at 1920px forms stretch across ~1575px.
9. **The visual language is inconsistent, and the requested RemixIcon icon system is entirely absent.** `@remixicon/react` is installed but never imported; almost every action is a text label or a literal `+`/`×` glyph.
10. **The product has almost no contextual help.** Users are expected to guess provider URLs, mode semantics, MCP setup, tool scopes, and even hand-write A2A agent-card JSON in a textarea. There are no inline explanations, tooltips, examples, templates, or links to documentation.

---

## Severity model

- **P0 — Blocker:** feature is unusable or corrupts the session/app state.
- **P1 — High:** common flow fails, loses user work, or hides errors.
- **P2 — Medium:** significant polish/UX problem with a workaround.
- **P3 — Low:** cosmetic or minor accessibility issue.

---

## What worked

These flows were exercised successfully and should not be regressed while fixing the items below:

- Login with `admin` / `admin`; invalid login shows an error.
- Creating a DeepSeek provider, refreshing its models, and selecting `deepseek-v4-pro`.
- Creating an agent with tools (`read_text_file`, `list_directory`, `web_search`).
- Real streaming chat responses from DeepSeek.
- Tool execution: the agent listed the project root and summarized it.
- Attachments: uploaded text file was read correctly by the model.
- File mentions: `@README` search returned project files.
- Skills: `/` opened the skill picker.
- Session branching: editing an earlier turn creates a fork.
- Avatar upload, A2A card modal, LSP/session “About” dialog, API key creation/revocation plumbing.
- Dark mode generally works at the shell level.

---

## Findings

### A. Chat and conversation experience

#### A1. Markdown output has no visual styling — **P0**

**Evidence:** [review-23-markdown-reply.png](assets/review-23-markdown-reply.png), [review-27-table-code.png](assets/review-27-table-code.png)

Every Markdown element inside `.markdown-block` computes to the same style:

- `h1`, `h2`, `p`: `font-size: 16px`, `font-weight: 400`, `margin: 0`
- `ul`: `list-style-type: none`
- tables: no borders, cell padding, or alignment
- code blocks: only a subtle gray background; no language label, copy action, or syntax highlighting

Headings such as “Markdown Demo”, “A Sample Table”, and “Wrapping Up” are visually indistinguishable from body text. Lists appear as consecutive lines. Tables run together (“LanguageFirst ReleasedTyping…”).

**Root cause:** `apps/web/src/chat/MarkdownBlock.tsx` renders raw ReactMarkdown output into `.markdown-block`, but there is no CSS for `.markdown-block`, `.session-turn`, or `.session-messages`. `apps/web/src/chat/apps.css` only styles the app panel. Bulma’s global reset also removes default heading/list margins because the output is not wrapped in Bulma’s `.content`.

**Expected:** Typographic hierarchy, list bullets/numbering, table borders/padding, code block chrome, readable line length, and paragraph spacing.

---

#### A2. Mermaid diagrams rendered during streaming corrupt the whole page — **P0**

**Evidence:** [review-24-markdown-bottom.png](assets/review-24-markdown-bottom.png), [review-25-markdown-middle.png](assets/review-25-markdown-middle.png), [review-26-markdown-code-table.png](assets/review-26-markdown-code-table.png), [review-30-admin-roles.png](assets/review-30-admin-roles.png), [review-31-admin-users.png](assets/review-31-admin-users.png), [review-32-api-keys.png](assets/review-32-api-keys.png)

A normal request for a Mermaid diagram produced several full-viewport “Syntax error in text / mermaid version 12.3.0” blocks. They overwhelmed the answer, made the page ~6800px tall, and **remained visible after navigating to Admin, Users, and API keys**. The only recovery was a full browser reload.

After reloading the same session, the diagram rendered successfully. This proves the diagram itself was valid and the failure was caused by rendering incomplete streaming text.

**Root cause:** `apps/web/src/chat/MermaidBlock.tsx`

- `useEffect` calls `mermaid.render()` for every content update, including partial streaming Markdown.
- On parse failure, `mermaid.render()` injects an error SVG into the document; the component does not clean that node up.
- The `failed` state is never reset when `source` later becomes valid.
- React StrictMode double-invokes the effect, which amplifies duplicate error nodes.

**Expected:** Render Mermaid only when the code fence is complete (or debounce and validate first), render off-DOM, remove temporary error nodes, and show a compact fallback with the source and a “copy” action. Never let a single diagram error leak outside the message.

---

#### A3. No auto-scroll and no anchored composer — **P1**

**Evidence:** [review-54-essay-finished.png](assets/review-54-essay-finished.png), [review-54 measurement](#measurements)

After a long answer, the page stayed near the top (`scrollY: 74`, `scrollHeight: 2431`) with the start of the essay visible and the end far below. With the long Markdown demo, the post-answer measurement was `scrollY: 0`, `scrollHeight: 6798`.

The composer is part of the document flow, not a sticky footer. In a long conversation the user must scroll to the bottom to type, then scroll down again to read the new answer.

**Expected:** A scrollable message pane pinned between header and composer, auto-scroll when the user is already at the bottom, a “jump to latest” affordance when they are not, and an always-visible composer.

---

#### A4. Provider/runtime errors can be completely silent — **P1**

**Evidence:** [review-47-provider-error.png](assets/review-47-provider-error.png), [review-48-retry-not-available.png](assets/review-48-retry-not-available.png)

With an invalid DeepSeek key:

- The user message “Hello, are you there?” was stored and displayed.
- No assistant reply appeared.
- No error banner, toast, or retry control appeared.
- After restoring the key and sending another message, the transcript still contained the unanswered turn with no failure marker.

The backend log shows `ModelAuthenticationError: status_code: 401 ...` and `run not successful ... status=error`, so the failure is known server-side but never surfaced in the UI.

By contrast, an HTTP 500 on the message endpoint does show a raw banner: “Error: HTTP 500:” — but it clears the composer and offers no retry. (See [review-58-network-error.png](assets/review-58-network-error.png).)

**Expected:** Clear error state on the failed turn, actionable message (“Provider authentication failed”), retry/re-run action, and preservation of the user’s input. Provider errors should not look like an empty assistant response.

---

#### A5. API failures are converted into empty data or success — **P1**

**Evidence:** [review-56-refresh-error-toast.png](assets/review-56-refresh-error-toast.png), [review-57-projects-500-empty.png](assets/review-57-projects-500-empty.png), [review-58-network-error.png](assets/review-58-network-error.png)

Several endpoint wrappers ignore the `error` returned by `openapi-fetch`:

- `refreshModels` (`apps/web/src/api/endpoints.ts:110`) returns `data ?? []`. A 500 from `/providers/{id}/models/refresh` produced the success toast **“Refreshed 0 models”** instead of an error.
- `fetchProjects` (`apps/web/src/api/endpoints.ts:18`) returns `data ?? []`. Mocking a 500 for `GET /projects` made the sidebar silently render no projects instead of the existing “Failed to load projects” branch.
- The same pattern exists in several list fetchers. During a failed message refetch, the visible conversation disappeared because messages became `[]`.

**Expected:** Throw or return a typed error; render list-level error states with retry; never report a failed operation as a success count.

---

#### A6. Reasoning and tool-call traces are transient and effectively invisible — **P1**

**Evidence:** [review-28-tool-call.png](assets/review-28-tool-call.png), [review-53-running-no-stop.png](assets/review-53-running-no-stop.png)

While the agent ran `list_directory`, tool events were streamed and available live. Once the run completed and messages were refetched, the transcript contained only the user prompt and the final assistant summary. The tool name, arguments, and result were gone.

Reasoning has the same problem, with an extra visibility issue: `ReasoningBlock` renders a `<details>` element that is **collapsed by default** (its summary is just “Reasoning”), so even while it is present most users will not notice it. After the run it disappears entirely.

**Root cause:** `apps/web/src/chat/useChat.ts` stores reasoning and tool calls only in transient React state (`reasoning`, `toolCalls`). `SessionPage` renders them only from that live state and then calls `chat.reset()` after refetch; the messages API persists only user/assistant text turns. There is no persisted step/trace model in the transcript.

**Expected:** Persisted reasoning and tool-call steps in the transcript, with a clear collapsed summary such as “Reasoning · 4 steps” and “3 tool calls”, expandable for arguments/results. At minimum, tool calls should remain visible after the run, and reasoning should be opt-in but discoverable rather than hidden in an unlabeled disclosure.

---

#### A7. Attachments are invisible after sending — **P1**

**Evidence:** [review-40-attachment-chip.png](assets/review-40-attachment-chip.png), [review-41-attachment-sent.png](assets/review-41-attachment-sent.png)

The composer shows an attachment chip before sending and the model successfully reads the file. After sending, the transcript shows only the text prompt; there is no filename, thumbnail, or attachment count. A user returning to the session cannot tell what was attached.

**Expected:** Persist attachment metadata on the user turn and render chips/thumbnails in history.

---

#### A8. “Edit” silently enters a destructive fork mode — **P1**

**Evidence:** [review-39-edit-fork.png](assets/review-39-edit-fork.png), [review-41-attachment-sent.png](assets/review-41-attachment-sent.png)

Clicking **Edit** on an earlier user message fills the composer with that text and sets fork mode, but the UI gives no banner, badge, or explanation. Sending the edited text replaced the visible history with a new branch (the transcript dropped all later turns). There is no “editing from this turn” indicator and no cancel affordance beyond reloading or manually clearing.

**Expected:** A visible “Replying from this turn / starting a new branch” state with a cancel button, plus a branch indicator in the transcript.

---

#### A9. No stop/cancel while a run is in progress — **P2**

**Evidence:** [review-53-running-no-stop.png](assets/review-53-running-no-stop.png)

While a long essay was streaming, `Send` was disabled and no stop control replaced it. The only way out is to wait or navigate away. This is particularly painful for long tool runs or loops.

**Expected:** A “Stop” button that aborts the run and preserves partial output.

---

#### A10. Enter does not send; no shortcut hint — **P2**

**Evidence:** [review-44-enter-key.png](assets/review-44-enter-key.png)

Pressing Enter in the message composer inserts a newline. There is no “Enter to send / Shift+Enter for newline” hint. Users accustomed to chat UIs will repeatedly type a message and wonder why nothing happened.

**Expected:** Enter sends (with Shift+Enter for newline) or an explicit visible hint/button behavior.

---

#### A11. Session page has almost no context — **P2**

**Evidence:** [review-21-session-created.png](assets/review-21-session-created.png)

The page heading is “Session”. The sidebar calls every session “Session 1”, “Session 2”, etc. There is no project name, session title, agent description, model name, or created/updated time in the main view, and no rename action. In a multi-session workspace this becomes hard to navigate.

---

#### A12. No visible “thinking/running” indicator in the chat — **P1**

**Evidence:** [review-53-running-no-stop.png](assets/review-53-running-no-stop.png)

While the model was running, the only state change was that the `Send` button was disabled. There was no spinner, “Thinking…”, streaming skeleton, agent activity line, or status near the conversation. Because the composer is below the fold in long sessions, even the disabled button is often not visible, so the app can look completely idle while the model is working.

`Composer` passes `loading={running}` to the Mantine `Send` button, which renders a spinner *inside the button only* (`apps/web/src/chat/Composer.tsx`). There is no run status in the message pane and no indication of which tool/reasoning step is active.

**Expected:** A persistent inline status in the conversation (“Thinking…”, “Running `list_directory`…”, “Waiting for provider…”) plus a visible spinner/progress state, independent of scroll position. Pair it with the stop control from A9.

---

### B. Data integrity and validation

#### B1. Blank names are accepted — **P1**

**Evidence:** [review-15-empty-project-submit.png](assets/review-15-empty-project-submit.png), [review-64-empty-provider.png](assets/review-64-empty-provider.png), [review-65-empty-agent-submit.png](assets/review-65-empty-agent-submit.png)

- **New project** with empty Name and Path created a project that renders as an unnamed sidebar entry with only “Edit + ×”.
- **Create provider** with every field empty created a provider row with a blank name and kind `generic`.
- **Create agent** with an empty model/name silently does nothing, with no validation message.

**Expected:** Required-field validation, disabled submit until valid, inline field errors, and server-side rejection of blank names.

---

#### B2. Project paths are not validated — **P1**

**Evidence:** [review-37-invalid-project-path.png](assets/review-37-invalid-project-path.png)

A project with path `C:\definitely\not\a\real\path` was created successfully. Sessions can then be created against it, and tools/LSP will fail later in confusing ways.

**Expected:** Validate that the path exists, is a directory, and is readable; show an inline error; optionally offer a folder picker.

---

#### B3. Destructive actions are inconsistent — **P1**

**Evidence:** [review-16-project-deleted-no-confirm.png](assets/review-16-project-deleted-no-confirm.png), [review-59-provider-delete-no-confirm.png](assets/review-59-provider-delete-no-confirm.png)

- Project delete: immediate, no confirmation, small “×” icon that is easy to hit by accident.
- Provider delete: immediate, no confirmation.
- Agent delete: immediate (same pattern).
- Session delete: confirmation modal (“Delete session?”).

**Expected:** A consistent confirmation/undo pattern for every destructive action, with the object name in the message and a red confirm button.

---

#### B4. Empty session submission gives no feedback — **P2**

**Evidence:** [review-20-new-session-empty-submit.png](assets/review-20-new-session-empty-submit.png)

Clicking **Create** in “New session” with no agent selected leaves the dialog open and does nothing. No inline error or disabled state explains why.

---

#### B5. Static “Session N” naming and no rename — **P2**

Session names are derived from creation order. There is no title, auto-title from the first message, or rename control. Combined with no timestamps/preview, the sidebar becomes unusable after a handful of sessions.

---

### C. Layout, navigation, and visual quality

#### C1. Mobile layout is effectively unusable — **P1**

**Evidence:** [review-35-mobile-home.png](assets/review-35-mobile-home.png), [review-36-mobile-session.png](assets/review-36-mobile-session.png)

At 390×844:

- The top navigation stacks every link vertically instead of collapsing into a menu.
- The project sidebar takes the full width and pushes page content down.
- Project action links (“Edit”, “+”, “×”) are spread to the far right with large empty gaps.
- Session content overflows horizontally (`scrollWidth: 402` vs `clientWidth: 390`).

**Expected:** A responsive shell with a collapsible nav/drawer, a collapsible project sidebar, and a chat layout that fits small screens.

---

#### C2. No max-width at large screens — **P1**

**Evidence:** [review-61-wide-providers.png](assets/review-61-wide-providers.png)

At 1920px the provider form stretches from x≈340 to x≈1896, producing single-line text fields around 1550px wide and very long reading lines. There is no content container or readable max-width.

---

#### C3. Home is blank — **P2**

**Evidence:** [review-03-home.png](assets/review-03-home.png)

After login, the home page contains only the word “Home”. There is no onboarding, recent sessions, project summary, or primary CTA (the only CTA is “New project” in the sidebar). A first-time user has no idea what to do next.

---

#### C4. Empty states are missing — **P2**

**Evidence:** [review-04-providers.png](assets/review-04-providers.png), [review-32-api-keys.png](assets/review-32-api-keys.png)

Providers, models, agents, API keys, and skills tables render an empty header row with no explanation or CTA. The provider page also leaves a large empty creation form visible above the empty table.

**Expected:** Purpose-built empty states (“No providers yet — add your first provider”, “Create your first API key”) with a CTA.

---

#### C5. Unknown routes render a blank page — **P2**

**Evidence:** [review-62-404-route.png](assets/review-62-404-route.png)

`/does-not-exist` renders a completely white page with no shell, message, or way back. `App.tsx` has no catch-all route.

---

#### C6. Invalid session IDs render a usable chat shell — **P2**

**Evidence:** [review-63-bad-session.png](assets/review-63-bad-session.png)

`/sessions/deadbeef` shows the full “Session” page with composer and Send button, despite nine 404s in the console. Users can type and send against a non-existent session.

**Expected:** A “Session not found” state, disabled composer, and a link back to a valid project.

---

#### C7. No active navigation state — **P2**

The navbar uses plain `<Link>` elements with no active styling. On a directly loaded page (e.g. `/providers`) no nav item indicates the current section.

---

#### C8. Login page is bare and full-width — **P3**

**Evidence:** [review-01-login.png](assets/review-01-login.png), [review-02-login-error.png](assets/review-02-login-error.png)

The login form spans almost the full 1280px viewport, with no branding, container, or card. The error state works but pushes the form down without focusing or announcing the error.

Other login issues:

- Username/password inputs have no `autocomplete` attributes.
- No loading state on the submit button (double-submit possible).
- No show/hide password control.
- The password input does have `type="password"` (verified), so this is a polish issue, not a security flaw.

---

#### C9. Dark mode has low-contrast project actions — **P3**

**Evidence:** [review-60-dark-mode.png](assets/review-60-dark-mode.png)

The shell switches to dark correctly, but the sidebar’s “Edit / + / ×” text buttons are dim gray on a dark background. They are already hard to discover in light mode and become harder in dark mode.

---

#### C10. Sidebar project actions wrap into a vertical stack — **P2**

**Evidence:** [review-03-home.png](assets/review-03-home.png), [review-61-wide-providers.png](assets/review-61-wide-providers.png)

In the narrow `column is-2` sidebar, the project name and the “Edit / + / ×” actions sit on different lines, and the three actions render on **three separate rows** far to the right. The result reads like broken markup rather than a tree control.

**Root cause:** `apps/web/src/components/projects/ProjectTree.tsx` places three bare `<button>` elements inside a single `<span>` within a `is-flex is-justify-content-space-between` row. The sidebar is only ~160px wide, there is no `flex-wrap: nowrap`, no `white-space: nowrap`, no gap, no icon sizing, and no button styling. The buttons therefore wrap one per line.

The “×” is also ambiguous (close vs delete), and the same treatment is used for every session row.

---

### D. Provider, agent, and admin UX

#### D1. Provider API key is rendered in plain text — **P1**

**Evidence:** [review-04-providers.png](assets/review-04-providers.png), [review-46-provider-edit.png](assets/review-46-provider-edit.png)

The “API key” field is a normal text input; the key is fully visible while typing and in screen-sharing situations. The edit dialog hides it with “leave blank to keep”, which is good, but creation is not masked and there is no reveal toggle.

**Expected:** `type="password"` plus a reveal control, or a secret-managed field.

---

#### D2. No “Test connection” / no inline provider guidance — **P2**

Provider creation has no help for what Base URL/Models URL should be per kind (DeepSeek, OpenAI, Anthropic, Ollama). There is no test button; users discover bad URLs only through a toast or a model refresh.

---

#### D3. Model refresh reports success on failure — see A5 — **P1**

The toast “Refreshed 0 models” on a 500 response is actively misleading. It should say “Failed to refresh models” and preserve the previous model list.

---

#### D4. Admin tables have blank descriptions and destructive actions without confirmation — **P2**

**Evidence:** [review-29-admin.png](assets/review-29-admin.png), [review-30-admin-roles.png](assets/review-30-admin-roles.png), [review-31-admin-users.png](assets/review-31-admin-users.png)

- Every seeded permission has an empty Description column.
- Permissions/roles/users have red Delete buttons with no confirmation.
- The create-permission/permission-edit UX uses raw permission strings with no explanation of scope.
- Roles and users require multiple clicks (Roles/Permissions buttons) to discover assignments; the assignment dialogs are not visible from the list.

---

#### D5. A2A card ignores agent description — **P2**

**Evidence:** [review-49-a2a-modal.png](assets/review-49-a2a-modal.png)

The A2A card for agent “Reviewer” is prefilled with `"description": ""` despite the agent having “General review assistant”. Saving it would publish a less informative card than the agent metadata.

---

#### D6. Agent creation form is a long ungrouped wall — **P2**

**Evidence:** [review-09-agents-empty.png](assets/review-09-agents-empty.png), [review-10-agent-form-top.png](assets/review-10-agent-form-top.png), [review-11-agent-form-bottom.png](assets/review-11-agent-form-bottom.png)

Nineteen tool checkboxes, MCP servers, modes, sub-agents, photo, and submit are all in one vertical flow. The Create button is far below the fold on a 720p screen. There is no grouping (“Filesystem”, “Web”, “Terminal”), no select-all/clear, no “show advanced” toggle, and no search for tools.

The Modes section has two unlabeled text inputs (`ask`, `agent`) and “Write enabled” checkboxes, with no explanation of what a mode is or how it maps to tool permissions.

---

#### D7. API key creation allows empty scopes and gives no copy feedback — **P2**

**Evidence:** [review-32-api-keys.png](assets/review-32-api-keys.png)

- The Scopes field is empty by default; clicking Create produces a key with no scopes (and therefore no usable permissions) without warning.
- The “Copy” button gives no confirmation or state change.
- The created-key modal shows the secret in a normal text input; it is not auto-selected.

---

#### D8. Native file input leaks browser locale and looks unstyled — **P3**

**Evidence:** [review-11-agent-form-bottom.png](assets/review-11-agent-form-bottom.png)

The photo picker renders the native Windows/Chrome control in French (“Choisir un fichier / Aucun fichier choisi”) while the rest of the app is in English. It is also visually inconsistent with the Mantine controls.

---

### E. Overall visual styling and iconography

**Verdict:** this reads as a functional developer prototype, not a finished product UI. The core flows are present, but there is no visible design system, no icon language, and very little typographic or spatial hierarchy. As a rough product-quality score: **3/10 visual design**, **7/10 functional completeness**. The gap is entirely in the presentation layer, not the backend capability.

| Area | Assessment |
|---|---|
| Information hierarchy | 2/10 — headings, body text, labels, and metadata often share the same weight/size |
| Component consistency | 3/10 — Mantine forms, Bulma `.box`/`.title`/`.button`, raw `<button>` elements, native file inputs, and raw `<pre>` all coexist |
| Iconography | 1/10 — no icons at all despite an explicit requirement and an installed library |
| Chat readability | 2/10 — unstyled Markdown, low-contrast role labels, visible “Copy Markdown” on every message |
| Responsiveness | 2/10 — vertical nav/sidebar stack on mobile, horizontal overflow, no max-width on desktop |
| Empty/error states | 2/10 — empty tables, blank Home, silent failures, raw HTTP strings |
| Dark mode | 6/10 — works at the shell level; sidebar action links lose contrast |
| Visual polish | 3/10 — large full-width fields, uncontrolled spacing, inconsistent alignment |

#### E1. RemixIcon is installed but never used — **P1 (explicit requirement miss)**

**Evidence:** [review-03-home.png](assets/review-03-home.png), [review-21-session-created.png](assets/review-21-session-created.png), [review-29-admin.png](assets/review-29-admin.png)

`apps/web/package.json` declares `"@remixicon/react": "^4.9.0"`, but there is **zero usage** of `@remixicon/react` or any `Ri*` icon component in `apps/web/src`. Every action is expressed as text or a literal glyph:

- Project tree: `Edit`, `+`, `×`
- Composer: `Attach`, `Dictate`, `Send`
- Assistant message: `Copy Markdown`, `Copy diagram`
- Nav: `Agents`, `Providers`, `Admin`, `API keys`, `Skills` with no icons
- Tables: text buttons (`Refresh models`, `Edit`, `Delete`, `Revoke`, `A2A`)

The `+` and `×` are especially problematic: they are ambiguous (add session? close? delete?), tiny, unlabeled visually, and stacked vertically in the sidebar. This is not a subjective polish issue — it is a missed explicit requirement.

**Expected:** A consistent RemixIcon set across navigation, primary actions, destructive actions, file/attachment actions, copy controls, tool-call rows, and status indicators. Icon-only actions need tooltips and accessible names; destructive actions should use a trash icon, not `×`.

#### E2. The styling is a three-library collision — **P1**

`apps/web/src/main.tsx` imports Mantine CSS, then Bulma CSS. The app then uses:

- Bulma shell classes (`navbar`, `columns`, `column is-2`, `box`, `title`, `button`, `notification`, `menu-list`)
- Mantine inputs, modals, tabs, selects, tables, notifications
- Raw HTML buttons in `ProjectTree`
- Raw `<pre>` for user messages
- Native `<input type="file">` for avatars and attachments
- ReactMarkdown output with **no CSS at all**

The result is visibly inconsistent: Mantine fields are large and full-width; Bulma `.title` headings are oversized; user messages are monospace gray bars; assistant Markdown is flat 16px text; project actions are browser-default buttons; the file picker leaks the OS/browser language (“Choisir un fichier”). Bulma’s global reset is also what strips heading margins and list bullets from Markdown, and the Mantine/Bulma import order makes the cascade fragile.

**Expected:** Pick one primary styling approach (Mantine is already there and supports theming/icons), define a small set of design tokens (spacing, type scale, colors, radii), and use them consistently. If Bulma remains for layout, scope it so it cannot reset chat typography.

#### E3. There is no visual hierarchy in the chat — **P1**

**Evidence:** [review-23-markdown-reply.png](assets/review-23-markdown-reply.png), [review-27-table-code.png](assets/review-27-table-code.png)

The most important surface in an agent product — the assistant answer — has the weakest styling. Message role labels (`user`, `assistant`) are tiny lowercase gray text; there is no avatar or timestamp; user turns are flat gray blocks; assistant turns have no container; the “Copy Markdown” button competes with the answer; code blocks have no header, language label, or copy button; tables have no borders or alignment.

This is not merely cosmetic. It makes long agent output hard to scan, hides structure, and makes tool results and diagrams feel like debug output.

#### E4. Forms are visually oversized and unstructured — **P1**

**Evidence:** [review-09-agents-empty.png](assets/review-09-agents-empty.png), [review-61-wide-providers.png](assets/review-61-wide-providers.png)

Provider and agent forms span the full content column with no max-width, grouping, or visual sections. At 1920px the fields are ~1550px wide. The agent form mixes a short name field, a multi-line instructions area, a 19-item checkbox grid, MCP URLs, modes, sub-agents, and a file picker without section cards or disclosure. The visual message is “database columns rendered as inputs”, not “configure an agent”.

#### E5. The shell is visually unresolved — **P2**

- The sidebar is a narrow Bulma column with no visual treatment, no icons, no section headers, and no active/selected state.
- The navbar has no brand mark, no active item, and no user menu.
- The Home page is a lone heading.
- Page backgrounds, cards, and table styles come from different libraries.
- There is no icon or visual cue for project vs. session vs. agent.
- The `Demo` project and its `Edit / + / ×` actions read as three separate floating controls because of wrapping.

#### E6. The product lacks design character — **P1 (product quality)**

**Evidence:** [review-03-home.png](assets/review-03-home.png), [review-21-session-created.png](assets/review-21-session-created.png), [review-29-admin.png](assets/review-29-admin.png), [review-34-skills.png](assets/review-34-skills.png), [review-60-dark-mode.png](assets/review-60-dark-mode.png)

The overall impression is “toy” rather than “product”:

- **No brand identity:** no logo/mark, no product-specific accent palette, no typographic voice, no iconography, no illustration, no empty-state art, no tagline. The visual identity is whatever Mantine and Bulma ship by default.
- **No spatial rhythm:** pages are a stack of full-width cards and tables; there is no max-width, no consistent gutter, no density choice, no visual grouping.
- **No surface hierarchy:** the shell, panels, tables, modals, and messages all use similar flat white surfaces, so nothing tells the eye what is primary.
- **No motion or feedback language:** no transition when a run starts, no streaming cursor, no tool “pulse”, no skeleton, no success/error motion. The app feels static even while an agent is working.
- **No product voice:** page headings are literals (“Home”, “Session”, “Admin”), empty tables are silent, and errors are raw strings (“Error: HTTP 500:”).
- **Chat does not feel like an agent workspace:** there is no tool timeline, no run status, no visible reasoning affordance, no agent identity beyond a tiny avatar, and no visual distinction between a chat turn, a tool call, and a system notice.
- **Dark mode is only an inversion:** it works mechanically, but does not establish a distinct mood or improve the chat surface.

The product does not need decoration; it needs a deliberate visual direction. For an agent workspace the natural direction is a **technical command center**: strong monospace metadata, a restrained neutral canvas, one confident accent color, crisp iconography, dense but breathable panels, and a clear hierarchy between the conversation, tool activity, and management surfaces. Right now none of those choices have been made, so the default libraries are making them instead.

What “character” would require in practice:

- A small brand kit: wordmark, accent color, neutral scale, semantic colors, type scale, radius, spacing, icon weight, motion durations.
- A real shell: max-width container, branded nav, active states, breadcrumbs, user menu, project/session identity.
- A chat surface designed as a first-class artifact: message containers, role identity, timestamps, copy actions, tool timeline, reasoning disclosure, streaming cursor, run status.
- Empty states and first-run guidance with a consistent illustration/icon language.
- Copywriting: product voice for headings, hints, errors, and confirmations.
- Remove one of Mantine/Bulma from the critical path, or fully scope Bulma to layout only, so the visual system is deterministic.

---

### F. Contextual help and learnability

**Verdict:** the UI assumes the user already knows the domain model. Almost every non-trivial concept is presented as a bare input with no explanation, example, default, validation, or documentation link. A user cannot discover how the system works from the UI.

#### F1. Complex concepts are presented as unlabeled inputs — **P1**

| Concept | Current UI | What the user has to guess |
|---|---|---|
| Provider `Kind` | A dropdown of `generic`, `openai_legacy`, `openai_responses`, `anthropic`, `moonshot`, `deepseek`, `ollama` | Which one to choose, which URLs are required, which API style each uses |
| `Base URL` / `Models URL` | Two blank text inputs | Exact URL format, whether `/v1` is required, whether a trailing slash matters, provider-specific examples |
| Model `Context window` | A number input with one sentence | What value to use, why it matters, what happens if wrong |
| Agent `Modes` | Two unlabeled text inputs (`ask`, `agent`) plus “Write enabled” | What a mode is, how it maps to tool permissions, how it appears in chat |
| Native tools | 19 opaque checkboxes (`read_multiple_files`, `list_directory_with_sizes`, …) | What each tool does, its risk, which are safe for read-only modes |
| MCP servers | One input with placeholder `https://server/mcp` | What MCP is, expected transport/config, auth, failure behavior |
| Sub-agents | An empty multi-select | What delegation means, how sub-sessions work, cost/latency implications |
| Model labels / priority | A label string and a priority number | What labels do, how model selection works, how priority is used |
| API scopes | A multi-select with raw strings | What each scope grants, what an empty scope set means |
| Additional allowed folders | A textarea with “One absolute path per line” | Why extra roots are needed, security implications, path format |
| A2A agent card | **A raw JSON textarea** | The entire A2A schema, required fields, valid skill shape, version semantics |

The same pattern appears in Admin: raw permission strings, raw role IDs, and assignment dialogs with no explanation of the authorization model.

#### F2. A2A agent card requires hand-written JSON in the UI — **P1**

**Evidence:** [review-49-a2a-modal.png](assets/review-49-a2a-modal.png)

Clicking **A2A** opens “A2A card: Reviewer” with a `Textarea` labeled “Agent card (JSON)” and a prefilled object:

```json
{
  "name": "Reviewer",
  "description": "",
  "version": "1.0.0",
  "skills": []
}
```

This is not acceptable for a product UI:

- The user must know the A2A AgentCard schema, field semantics, and valid `skills` structure.
- The default is wrong/undiscoverable: the agent has a description (“General review assistant”), but the card prefills `description: ""`.
- There is no schema, example, field help, or link to A2A documentation.
- Invalid input produces only a transient toast, “Invalid agent card JSON”, with no field-level error or line number.
- There is no preview of what an external A2A client will see.
- There is no “use agent metadata” action, no structured editor, and no template for skills.

**Expected:** a structured form for name, description, version, capabilities, and a repeatable skills editor (name, description, input/output modes, examples), with an optional “Advanced JSON” mode for power users. Validate against the schema inline, show a preview, and default the card from the agent’s existing metadata.

#### F3. There is essentially no help surface — **P2**

A search of `apps/web/src` for `Tooltip`, help components, or documentation links found no help UI. The only descriptive text in management forms is:

- “Optional token window for custom/local models”
- “One absolute path per line”

There is no:

- Inline help icon or tooltip next to complex fields.
- “What is this?” disclosure.
- Example values or “Use this template” action.
- Per-provider setup guide or “Test connection” button.
- Link to A2A/MCP/ACP docs or a local help page.
- First-run onboarding, guided setup, or sample data.
- Contextual empty states that explain what to do next.

#### F4. Errors teach nothing — **P2**

Provider refresh failures, invalid paths, malformed A2A JSON, blank names, and model authentication failures either disappear, show a generic toast, or show a raw HTTP status. There is no actionable guidance (“Check the API key”, “The path must exist on the server”, “Add at least one scope”, “This model does not support tool calls”).

**Expected:** Inline, field-level, specific errors with a next action; keep user input; log a correlation ID when appropriate.

---

### G. Accessibility and polish

- **Login autocomplete:** no `autocomplete="username"` / `"current-password"`; Chrome logs a DOM warning.
- **Live regions:** the login error and chat error banners are plain divs; no `role="alert"` and no focus move. Screen-reader users may miss them.
- **Chat role labels:** `user`/`assistant` are tiny unstyled paragraphs, not semantic message labels.
- **Icon buttons:** project actions are bare text (`Edit`, `+`, `×`) with aria-labels, but tiny hit areas and no tooltips.
- **Page title:** always “Agentbox”; no per-page titles for history or bookmarks.
- **Favicon:** `/favicon.ico` returns 404 on every page load (observed in the console).
- **No skip link/main landmark polish:** the main region exists, but the shell has no skip navigation.
- **Error copy:** raw `Error: HTTP 500:` is not actionable.

---

### H. Backend/observability issues observed during the review

#### H1. Provider authentication failure breaks loguru logging — **P1 (operational)**

When DeepSeek returned 401, loguru failed to serialize `ModelAuthenticationError` into its multiprocessing queue:

```
_pickle.PicklingError: Can't pickle <class 'pydantic_ai.exceptions.ModelAuthenticationError'>:
it's not the same object as pydantic_ai.exceptions.ModelAuthenticationError
--- End of logging error ---
```

The user-visible part is the silent failure in A4; the operational part is that the detailed exception may be missing from logs exactly when you need it.

#### H2. Multiple 404s from an invalid session — **P3**

`/sessions/deadbeef` triggers 404s for session, LSP, and plan endpoints (repeated due to refetch/StrictMode). Harmless but noisy and contributes to the broken-shell behavior in C6.

---

## Measurements captured

- Markdown demo after streaming: `window.scrollY = 0`, `document.body.scrollHeight = 6798`, `innerHeight = 720`.
- Essay after streaming: `window.scrollY = 74`, `document.body.scrollHeight = 2431`.
- Mobile session: `document.documentElement.scrollWidth = 402`, `clientWidth = 390`.
- Markdown computed styles: `h1`, `h2`, `p` all `16px / 400 / margin 0`; `ul` `list-style-type: none`.

---

## Reproduction notes

The backend was run with a temporary database and JWT secret:

```powershell
$env:DATABASE_URL='sqlite+aiosqlite:///./review.db'
$env:JWT_SECRET='review-secret-review-secret-review-32'
$env:SKILLS_USER_DIR='./review-skills'
uv run python -m agentbox_api.dev_server
```

Frontend:

```powershell
cd apps/web
bun run dev -- --port 5173
```

Login: `admin` / `admin`.

Focused repros:

1. **Markdown:** create a session, ask for headings/list/table/code/Mermaid; observe flat typography and unstyled table.
2. **Mermaid corruption:** ask for a Mermaid diagram, then navigate to `/admin` and `/api-keys` without reloading; error blocks persist.
3. **Silent provider error:** edit the provider key to an invalid value, send a message; no error appears. Restore the key afterward.
4. **Error-as-success:** create a provider with an unreachable Models URL, click “Refresh models”; observe “Refreshed 0 models” on a 500.
5. **Blank data:** open “New project”, submit empty; open “Create provider”, submit empty; both create blank rows.
6. **Destructive actions:** delete a project/provider/agent; compare with session delete (which confirms).
7. **Responsive:** resize to 390×844; observe stacked nav/sidebar and horizontal overflow.
8. **404s:** open `/does-not-exist` and `/sessions/deadbeef`.

---

## Recommended priority

### Fix first (P0/P1)

1. Add a Markdown/chat stylesheet (or wrap Markdown in a `.content`-like scope) with headings, paragraph spacing, lists, tables, code, blockquotes, links, and max line length.
2. Stop rendering Mermaid on partial source; validate/parse before render, clean up injected nodes, reset failure state, and render a compact fallback.
3. Implement a message pane with auto-scroll, sticky composer, an explicit “thinking/running” indicator, a stop control, and “jump to latest”.
4. Surface provider/run failures as a per-turn error with retry and preserved input.
5. Stop swallowing API errors in `endpoints.ts`; add list-level error/retry states.
6. Persist and render tool calls and attachments in the transcript.
7. Add required-field validation and path validation; reject blank names server-side as well.
8. Add consistent confirmation/undo for every destructive action.
9. Add an “editing/forking from this turn” banner with cancel.
10. Make the shell responsive (collapsible nav and sidebar, no horizontal overflow).
11. Mask provider API keys.
12. Adopt `@remixicon/react` as the single icon system across nav, actions, copy controls, tool calls, and empty states; use a trash icon (not `×`) for deletion, and add tooltips/accessible names for icon-only buttons.
13. Define design tokens and a consistent component style: one typography scale, one spacing scale, one field width strategy, a max content width, and a dark-mode palette. Scope or remove Bulma where it resets chat typography.
14. Establish a real visual identity: wordmark, accent palette, type voice, icon language, motion/feedback language, designed empty states, and a chat surface with clear message/tool/reasoning hierarchy. The current library-default look is the main reason the product reads as a toy.
15. Add in-product contextual help: per-provider setup examples, field tooltips, mode/tool descriptions, MCP templates, API scope descriptions, “Test connection”, docs links, and guided empty states.
16. Replace the A2A raw JSON textarea with a structured card editor (name, description, version, skills), schema validation, preview, and “derive from agent metadata”, with JSON reserved for an advanced mode.

### Next (P2)

- Empty states on every management page.
- Home dashboard/onboarding with recent sessions and a primary CTA.
- 404 route and “session not found” states.
- Active nav styling; page titles; favicon.
- Session titles (auto-title + rename).
- Group/collapse the agent tool picker.
- Stop button while running.
- Enter-to-send hint/behavior.
- Admin permission descriptions and assignment discoverability.

### Later (P3)

- Login layout/card and autocomplete attributes.
- Dark-mode contrast for sidebar actions.
- Copy feedback on “Copy Markdown”, “Copy diagram”, API key copy, and code blocks.
- Replace native file inputs with styled controls.
- Fix loguru exception serialization for provider errors.

---

## Evidence index

| Screenshot | Finding |
|---|---|
| [review-01-login.png](assets/review-01-login.png) | Bare full-width login |
| [review-02-login-error.png](assets/review-02-login-error.png) | Login error state |
| [review-03-home.png](assets/review-03-home.png) | Blank Home + sidebar layout |
| [review-04-providers.png](assets/review-04-providers.png) | Empty provider state, plain-text API key |
| [review-08-models-tab.png](assets/review-08-models-tab.png) | Models table, DeepSeek models |
| [review-09-agents-empty.png](assets/review-09-agents-empty.png) | Ungrouped agent form |
| [review-11-agent-form-bottom.png](assets/review-11-agent-form-bottom.png) | Unstyled file input, modes UI |
| [review-15-empty-project-submit.png](assets/review-15-empty-project-submit.png) | Blank project created |
| [review-16-project-deleted-no-confirm.png](assets/review-16-project-deleted-no-confirm.png) | Immediate project delete |
| [review-20-new-session-empty-submit.png](assets/review-20-new-session-empty-submit.png) | Silent empty session submit |
| [review-21-session-created.png](assets/review-21-session-created.png) | Session page context |
| [review-23-markdown-reply.png](assets/review-23-markdown-reply.png) | Unstyled Markdown |
| [review-24-markdown-bottom.png](assets/review-24-markdown-bottom.png) | Mermaid error explosion |
| [review-25-markdown-middle.png](assets/review-25-markdown-middle.png) | Mermaid errors fill page |
| [review-27-table-code.png](assets/review-27-table-code.png) | Unstyled table/code |
| [review-28-tool-call.png](assets/review-28-tool-call.png) | Tool trace absent after completion |
| [review-30-admin-roles.png](assets/review-30-admin-roles.png) | Mermaid errors persist on Admin |
| [review-31-admin-users.png](assets/review-31-admin-users.png) | Mermaid errors persist on Users |
| [review-32-api-keys.png](assets/review-32-api-keys.png) | Mermaid errors persist on API keys |
| [review-35-mobile-home.png](assets/review-35-mobile-home.png) | Broken mobile shell |
| [review-36-mobile-session.png](assets/review-36-mobile-session.png) | Mobile overflow |
| [review-37-invalid-project-path.png](assets/review-37-invalid-project-path.png) | Invalid path accepted |
| [review-39-edit-fork.png](assets/review-39-edit-fork.png) | Silent fork mode |
| [review-41-attachment-sent.png](assets/review-41-attachment-sent.png) | Attachment missing from history |
| [review-44-enter-key.png](assets/review-44-enter-key.png) | Enter inserts newline |
| [review-47-provider-error.png](assets/review-47-provider-error.png) | Silent provider auth failure |
| [review-49-a2a-modal.png](assets/review-49-a2a-modal.png) | A2A card as raw JSON |
| [review-53-running-no-stop.png](assets/review-53-running-no-stop.png) | No running indicator or stop control |
| [review-54-essay-finished.png](assets/review-54-essay-finished.png) | No auto-scroll |
| [review-56-refresh-error-toast.png](assets/review-56-refresh-error-toast.png) | Failed refresh shown as success |
| [review-57-projects-500-empty.png](assets/review-57-projects-500-empty.png) | 500 shown as empty sidebar |
| [review-58-network-error.png](assets/review-58-network-error.png) | Raw HTTP 500 banner |
| [review-59-provider-delete-no-confirm.png](assets/review-59-provider-delete-no-confirm.png) | Immediate provider delete |
| [review-60-dark-mode.png](assets/review-60-dark-mode.png) | Dark-mode sidebar contrast |
| [review-61-wide-providers.png](assets/review-61-wide-providers.png) | No max-width at 1920px |
| [review-62-404-route.png](assets/review-62-404-route.png) | Blank unknown route |
| [review-63-bad-session.png](assets/review-63-bad-session.png) | Invalid session renders chat shell |
| [review-64-empty-provider.png](assets/review-64-empty-provider.png) | Blank provider created |
| [review-65-empty-agent-submit.png](assets/review-65-empty-agent-submit.png) | Silent empty agent submit |
