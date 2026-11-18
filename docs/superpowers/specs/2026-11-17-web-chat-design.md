# Chat (Core + Edit/Fork + Composer) — Design Specification

- **Date:** 2026-11-17
- **Status:** Draft (brainstormed, pending implementation plan)
- **Sub-project:** Frontend #5 — the agentic chat: AG-UI streaming, rich rendering, history/resume, mode switching, edit/fork, and a composer with attachments (multimodal) and speech-to-text.

## 1. Context and Scope

The chat is the core interaction: a session on a project where the agent streams responses. It consumes the backend's `POST /sessions/{id}/messages` (AG-UI SSE) and is validated end-to-end with Playwright against the real stack. Coverage status of the whole spec is tracked in `docs/ROADMAP.md`.

### 1.1 What this sub-project encompasses

- Backend: history endpoint, send options (`mode`, `fork_from_turn_id`, `attachment_ids`), attachment upload/storage (+ migration), harness multimodal prompt, and a deterministic `test` provider.
- Frontend: AG-UI client, `SessionPage` rich rendering (Markdown, Mermaid, reasoning, tool calls), history/resume, mode selector, edit/fork, and a composer with attachments + speech-to-text.
- E2E tests on the real stack.

### 1.2 Deferred (tracked in `docs/ROADMAP.md`)

- **Autocomplete**: `/` skills (skills system not built) and `@` filenames (needs a file-listing endpoint).
- **MCP Apps** left-hand tabs (separate sub-project).
- Attachments are **not replayed on resume** (history stores text; attachments are per-turn).

### 1.3 Dependencies

- `agentbox-api`, `agentbox-harness`, `agentbox-models`; `apps/web` (scaffold/auth/tree/management).

## 2. Decisions and Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **`@ag-ui/client`** (subclassed for our endpoint) for stream consumption. | Reuses the spec-compliant SSE transport and event reducer. |
| D2 | **Attachments are multimodal** (`pydantic-ai` `BinaryContent`) to the model. | The spec allows attachments; the model sees them directly (vision/document models). |
| D3 | Attachments are **uploaded then referenced** by id on send. | Keeps the send JSON (clean for the AG-UI client); supports multiple files. |
| D4 | **Edit/fork** via `fork_from_turn_id` (branch the run from a prior turn). | Matches the spec ("conversation restarts from the edited question") with an immutable log. |
| D5 | Mode passed per send (`mode`), default `agent`. | Enables the Ask/Agent switch described in the spec. |
| D6 | A **`test` provider kind** → `TestModel(custom_output_text="Hello from the test provider")`. | Deterministic streaming for E2E without a real LLM. |
| D7 | History returns the **active branch** (root→latest leaf). | The UI renders one linear conversation; branches remain in the immutable log. |
| D8 | E2E-first validation (per the user's directive). | Mocked tests don't prove functionality. |

## 3. Backend

### 3.1 History
- `GET /sessions/{sid}/messages -> list[MessageRead]` — the active branch: from the latest leaf (max `created_at` among childless turns) up to the root, ordered root→leaf. `MessageRead = {id, role, content, parent_id, created_at}`.

### 3.2 Send (extended)
- `POST /sessions/{sid}/messages` body: `{content: str, mode?: str, fork_from_turn_id?: str, attachment_ids?: list[str]}`.
- Behavior: load attachments (bytes) → build multimodal prompt `[content, BinaryContent(...), …]`; set the run's start turn to `fork_from_turn_id` (else the computed leaf); use `mode` (default `agent`) resolved from the agent's `mode_definitions`; run the harness and stream AG-UI.

### 3.3 Attachments
- New table `session_attachments` (`id, session_id, media_type, filename, data, created_at`) + Alembic migration.
- `POST /sessions/{sid}/attachments` (multipart `file`) → store → `{id, media_type, filename}`.

### 3.4 Harness multimodal
- `Harness.run(session, user_message, bus, prompt_override=None)`: if `prompt_override` is set, pass it to `run_stream_events` as the user prompt (`Sequence[UserContent]`); the user turn still stores `user_message` (text) for the log.

### 3.5 Test provider
- `resolve_model`: `kind == "test"` → `TestModel(custom_output_text="Hello from the test provider")`.

### 3.6 Schema
- Regenerate `apps/web/openapi.json` + `schema.d.ts`.

## 4. Frontend

### 4.1 AG-UI client
- A `HttpAgent` subclass (or `AbstractAgent` implementation) targeting `${VITE_API_URL}/sessions/{sid}/messages`: sets `Authorization`, POSTs `{content, mode, fork_from_turn_id, attachment_ids}`, consumes the SSE event stream; the SDK reducer accumulates text/reasoning/tool calls.

### 4.2 `SessionPage`
- On mount: load history (`GET /messages`).
- Renders turns:
  - **User** turns: text + an **Edit** action.
  - **Assistant** turns: Markdown (`react-markdown` + `remark-gfm`); **Mermaid** code blocks rendered as diagrams (`mermaid`) with **pan/zoom** (`react-zoom-pan-pinch`) and a **copy-source** button; **reasoning** in a collapsible block; **tool calls** (name/args/result) collapsible.
- **Streaming**: the in-flight assistant message updates live from the AG-UI agent.
- **Mode selector** (from the agent's `mode_definitions`), default `agent`.
- **Edit/fork**: editing a user turn prefills the composer; sending uses `fork_from_turn_id = edited turn's parent_id`; then reload the active branch.

### 4.3 Composer
- Bulma textarea + **Send** + **mode select** + **📎 attach** + **🎤 speech-to-text**.
- **Attachments**: choose files → `POST /attachments` (upload) → show chips → included as `attachment_ids` on send.
- **Speech-to-text**: Web Speech API (`SpeechRecognition`/`webkitSpeechRecognition`) — start/stop; append transcript to the textarea; the mic is hidden when unsupported.

### 4.4 Libraries
- `@ag-ui/client` (+ `@ag-ui/core` types), `react-markdown`, `remark-gfm`, `mermaid`, `react-zoom-pan-pinch`; a local TS declaration for `SpeechRecognition`.

## 5. Testing (E2E-first)

- **Backend pytest**: active-branch `/messages`; `mode` honored; `fork_from_turn_id` branches; attachment stored + retrievable; `test` provider resolves.
- **Playwright E2E** (real stack, `test` provider): open a session → send text → assert the streamed text renders (Markdown) → attach a file → chip appears → send succeeds → edit a question → conversation forks/restarts. Speech-to-text: assert the mic button is present and, with `SpeechRecognition` stubbed via `addInitScript`, clicking appends text.

## 6. Error Handling

- Stream `RUN_ERROR` → an error bubble in the chat.
- Upload/send failures → Mantine notification.

## 7. Open Items / Future Work

- Autocomplete (`/`, `@`), MCP Apps tabs — see `docs/ROADMAP.md`.
- Attachments persistence across resume (replay `BinaryContent`) — future.

## References

- Initial spec — `docs/initial_spec.md`; roadmap — `docs/ROADMAP.md`.
- AG-UI: `https://docs.ag-ui.com/` (`@ag-ui/client`).
- MCP Apps reference: `https://github.com/jrialland/minimal-agent-example`.
