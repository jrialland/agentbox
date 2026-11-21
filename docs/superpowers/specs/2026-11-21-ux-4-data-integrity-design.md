# UX-4 - Data Integrity, Errors, and Navigation States

- **Date:** 2026-11-21
- **Status:** Draft (design approved; pending spec review)
- **Sub-project:** UX-4 - required-field and path validation, destructive confirmations, API error propagation, 404 and session-not-found states, session titles, admin permission guidance, and safe provider-error logging.
- **Source:** [`docs/reviews/2026-11-20-ux-review/report.md`](../../reviews/2026-11-20-ux-review/report.md) findings B1-B5, C5-C6, C7, D4, H1-H2, and the remaining parts of A4-A5.
- **Roadmap:** `UX-4` in [`docs/ROADMAP.md`](../../ROADMAP.md).

## 1. Context and scope

UX-1 through UX-3 established the visual system, chat surface, structured editors, and in-app guidance. The remaining product-quality gap is trust: forms can submit invalid data, failed reads look like empty data, destructive actions are inconsistent, bad routes and session IDs render misleading shells, sessions are indistinguishable in the sidebar, and a provider exception can break the logging sink.

UX-4 adds the missing integrity and recovery layer without redesigning the established visual language.

### 1.1 In scope

- Shared API error normalization and retryable list/section error states.
- Required-field, path, URL, and empty-selection validation in the UI and API.
- Consistent standard and type-to-confirm destructive actions.
- An authenticated 404 route and a focused session-not-found state.
- Automatic first-message session titles and manual rename.
- Built-in descriptions for core admin permissions.
- Safe traceback logging for provider and MCP failures.
- Unit, API, E2E, and screenshot coverage for the above.

### 1.2 Out of scope

- Duplicate-name restrictions and name-uniqueness changes.
- Undo-based deletion or soft-delete workflows.
- Active-navigation redesign; active navigation already exists and will only get a regression check.
- LLM-generated session titles.
- New session, provider, agent, A2A, MCP, or RBAC capabilities.
- A global read-error toast system.
- Unrelated refactors outside the files touched by UX-4.

### 1.3 Dependencies

- UX-1 design system and command shell.
- UX-2 chat error and retry components.
- UX-3 help, structured editors, and empty states.
- Existing FastAPI routers, SQLModel tables, Alembic setup, and React Query hooks.
- Loguru sinks configured with `enqueue=True`.

## 2. Goals and success criteria

- A failed API read never appears as a successful empty list or a false zero count.
- Every invalid form submission is blocked with an inline explanation; the API rejects the same invalid data.
- Every destructive action has an appropriate confirmation, and high-impact actions require typing the resource name.
- Unknown routes and invalid session IDs show deliberate, navigable states instead of blank or broken shells.
- Sessions are identifiable by a useful title and can be renamed.
- Provider authentication or runtime exceptions remain visible in logs even when the exception object is not picklable.
- Existing chat, provider, agent, A2A, MCP, skills, and RBAC behavior remains intact.

## 3. Decisions and rationale

| # | Decision | Rationale |
|---|---|---|
| D1 | **Typed API errors at one boundary.** | Central normalization prevents each page from inventing error shapes and preserves server detail. |
| D2 | **Read failures render local error/retry states.** | A failed section should be recoverable without blanking the whole application or showing a misleading empty state. |
| D3 | **Pragmatic validation in both UI and API.** | Fast client feedback plus server enforcement; duplicate names stay allowed and relative project paths keep working. |
| D4 | **Tiered destructive confirmation.** | High-impact resources require typing their name; lower-impact actions use a standard confirm without becoming friction-heavy. |
| D5 | **Dedicated 404 and session-not-found states.** | Blank routes and usable-but-broken chat shells hide mistakes; explicit states provide the next action. |
| D6 | **Session titles are deterministic and user-overridable.** | A first-message snippet is free, fast, and predictable; manual rename is never overwritten. |
| D7 | **Core permission descriptions are frontend-owned fallbacks.** | Existing installations get useful descriptions without a destructive data migration; custom descriptions still win. |
| D8 | **Log traceback text, not exception objects.** | Loguru's async queue must pickle records; strings are safe while preserving diagnostic detail. |
| D9 | **No undo in UX-4.** | Confirmation is the chosen safety mechanism; undo/soft-delete needs a larger data-retention design. |

## 4. Architecture

### 4.1 API error boundary

Create `apps/web/src/api/errors.ts` with:

```ts
export class ApiError extends Error {
  status: number;
  detail: string;
  fields?: Record<string, string>;
}
```

- `status` is the HTTP status, or `0` for network failures.
- `detail` is the normalized server message or a caller-provided fallback.
- `fields` maps FastAPI validation locations to messages when the response is a structured 422.
- A normalizer accepts the `error` value from `openapi-fetch` plus a fallback and optional response status.
- The normalizer handles string details, `{ detail: string }`, and FastAPI validation arrays without throwing.

All `fetch*` functions in `apps/web/src/api/endpoints.ts` throw `ApiError` on failure. Successful empty responses still return `[]`. The existing intentional `fetchAgentCard` 404-to-null behavior is retained.

### 4.2 Query behavior

- The shared `QueryClient` retries at most once for network errors and 5xx responses; it does not retry 4xx.
- Session detail treats 404 as terminal and disables messages, LSP, and plan queries when the session is missing.
- Read queries expose `error`, `isError`, and `refetch` to their pages; pages never substitute `[]` for a failed request.
- Mutations keep targeted notifications but use `ApiError.detail` and `ApiError.fields` before falling back to a generic message.

### 4.3 Shared UI states

Add design-system patterns:

- `ErrorState`: icon, title, message, Retry action, optional secondary action. Used for page- and section-level read failures.
- `NotFoundPage`: authenticated shell page with a 404 explanation and “Back to Home”.
- `SessionNotFound`: focused session state with “Back to Home” and “Browse projects”; no composer or chat panels.
- `ConfirmDialog` is extended with `requireText?: string` and pending/error handling rather than creating a second modal component.

Error states distinguish:

- loading;
- successful empty data;
- 404 not found;
- other API failure.

### 4.4 Validation helpers

Create `apps/web/src/lib/validation.ts` with small pure helpers:

- `requiredText(value)` — trims and rejects empty.
- `isHttpUrl(value)` — accepts empty values where the field is optional; otherwise requires HTTP(S).
- `isAbsolutePath(value)` — used for additional allowed folders.
- `firstFieldError(fields, name)` — maps server-side 422 fields into existing `FormField` errors.

Pages may keep their current field state; validation returns messages instead of introducing a form library.

### 4.5 Destructive-action flow

Both confirmation tiers use `ConfirmDialog`:

- **Standard confirm:** sessions, models, API key revoke, agent card removal.
- **Type-to-confirm:** projects, agents, providers, users, roles, permissions.

Type-to-confirm behavior:

- The dialog shows the exact resource name.
- The confirm button is disabled until the trimmed input exactly matches the trimmed resource name (case-sensitive).
- The resource name and “cannot be undone” consequence are always visible.
- Confirm is disabled while the mutation is pending.
- A failed mutation keeps the dialog open and displays the API error; success closes it and invalidates the affected queries.

### 4.6 Navigation and session titles

- Add a `*` route inside the authenticated shell that renders `NotFoundPage`.
- The 404 page does not replace the shell; navigation remains usable.
- Invalid session IDs render `SessionNotFound` rather than the chat shell.
- A session detail 5xx/network failure renders the standard retryable `ErrorState`.

Session titles:

- Add nullable `title` to `SessionRow` and `SessionDetail`.
- Generate a title from the first user prompt when the session has no title:
  - normalize whitespace;
  - use the current prompt content, including retry prompts;
  - keep at most 60 characters; when longer, keep the first 57 characters and append `...`.
- Manual rename sets the title and is never overwritten.
- Rename trims the value, rejects blank/oversized values, and is available from the session header and sidebar.
- Sidebar fallback for legacy/untitled sessions is `Session N`.
- Home recent sessions show `title ?? agent_id`.
- Session header shows the title or `Session`.

### 4.7 Admin permission descriptions

- Add a frontend map of built-in descriptions for the seeded core permissions.
- Display `stored description || built-in description || "No description"` in permission tables and role assignment labels.
- Custom descriptions always take precedence.
- No database backfill is required.

### 4.8 Safe exception logging

Add a small harness logging helper, for example `agentbox_harness/logging.py`:

```py
def log_exception(message: str, *args, **kwargs) -> None:
    """Log the current exception as traceback text, never as an object."""
```

- The helper captures the active exception with `traceback.format_exception`.
- It logs a single string through loguru with `exception=None`.
- Replace `logger.exception(...)` at the harness run boundary and API MCP relay with the helper.
- The asynchronous file sink remains enabled.
- Other logging behavior and formats stay unchanged.

## 5. Backend changes

### 5.1 Session title persistence

- Add `title: str | None = None` to `SessionRow`.
- Add an Alembic revision for the nullable column.
- Add `title` to `SessionDetail`.
- Existing sessions remain valid with `title = NULL`.

### 5.2 Session API contract

- `PATCH /sessions/{sid}` accepts `{ "title": string }`.
- Permission: existing `sessions:create`.
- The title is trimmed; blank and values over 120 characters are rejected with 422.
- Missing session returns 404.
- On the first chat turn for an untitled session, persist the derived title before starting the run.
- The title is derived once; manual rename is never replaced.

### 5.3 Validation contract

- Project creation: name after trimming is non-empty; path resolves to an existing directory; path may be relative.
- Project update: name is trimmed/non-empty; when extra roots are supplied, each must be an absolute existing directory.
- Provider/agent/role/permission names: trimmed/non-empty.
- Provider `base_url` and `models_url`, when supplied, must be HTTP(S) URLs.
- User creation: username, email, and password are non-blank.
- Empty agent selection for session creation is rejected in the UI and remains a 404/422 API error if bypassed.
- Validation failures return FastAPI 422 responses. The frontend surfaces a form-level error and maps known field errors when available.

### 5.4 Logging behavior

- Provider and MCP failures continue to produce a traceback in logs.
- The log record contains the exception type, message, and formatted traceback as text.
- No arbitrary exception object is sent through the enqueue queue.

## 6. Frontend changes

### 6.1 API and queries

- Add `errors.ts`; update `endpoints.ts`, `queries.ts`, and the QueryClient defaults.
- Add `useRenameSession` and invalidate `sessions`, the specific session, and Home data through session invalidation.
- After a chat run refreshes messages, invalidate `sessions` and the specific session so a newly auto-generated title appears in the sidebar and header without a reload.
- Add field-error mapping helpers for 422 responses.

### 6.2 Pages and components

- `ProjectPanel`: section error with retry; confirmed project/session deletion; session titles and inline rename; no false “No projects” state on failure.
- `HomePage`: stat cards show unavailable rather than zero on failure; recent sessions/projects show compact error states.
- `AgentsPage`/`AgentList`: delete confirmation; validation for create; page error state.
- `ProvidersPage`: provider delete confirmation; model delete standard confirmation; error states for providers/models; existing URL testing remains.
- `ApiKeysPage`: revoke confirmation; page error state; server validation errors.
- `AdminPage`: tab-level error states; permission/role/user validation; type-to-confirm deletes; permission descriptions.
- `SkillsPage`: list error state with retry.
- `SessionPage`: session-not-found gate; messages/plan error handling; title display and rename.
- `App.tsx`: authenticated 404 route.
- `NewProjectModal`, `NewSessionModal`, `AgentCreateDrawer`: inline validation and safe submit guards.

### 6.3 Session title UI

- Sidebar rows display the title or `Session N`.
- A rename action opens an inline text input; Enter saves, Escape cancels.
- The session header displays the title and exposes the same rename action.
- Renaming preserves all other session behavior and does not navigate away.

## 7. Data flow

### 7.1 Failed read

```text
openapi-fetch error
  -> ApiError
  -> React Query error state
  -> ErrorState / section error
  -> Retry calls refetch
```

No failed read may fall through to a successful empty-state branch.

### 7.2 Destructive action

```text
user clicks delete/revoke/remove
  -> shared confirm dialog (standard or type-to-confirm)
  -> mutation
  -> success: close + invalidate
  -> failure: keep open + show server detail
```

### 7.3 Session title

```text
first user turn
  -> title is null?
  -> derive normalized snippet
  -> persist title
  -> sidebar/header/home read title

manual rename
  -> PATCH /sessions/{sid}
  -> invalidate session queries
```

## 8. Testing

### 8.1 Backend

- Blank project/provider/agent/role/permission/user names return 422.
- Missing or non-directory project paths return 422; relative paths are accepted.
- Relative or missing extra roots return 422.
- Session title is generated once from the first user message.
- Manual rename overrides an existing title.
- Blank/oversized titles return 422; rename permission is enforced.
- A non-picklable exception is logged through the safe helper without breaking the sink.

### 8.2 Frontend

- `ApiError` normalization for string, object, validation-array, network, and unknown errors.
- Error-state rendering and retry behavior.
- Validation helpers and field-error mapping.
- Standard and type-to-confirm dialogs, including pending and failed mutations.
- 404 route and session-not-found behavior.
- Title display, auto-title result, rename save/cancel, and fallback labels.
- Admin permission-description fallback.

### 8.3 E2E

- Unknown route shows the 404 page inside the shell.
- Invalid session shows the session-not-found state without a composer or repeated 404 requests.
- Failed list query shows an error state and retry succeeds.
- Existing active-navigation styling remains active on directly loaded routes and after navigation.
- Empty project/provider/agent forms are blocked with inline errors.
- Empty session submission is blocked.
- High-impact delete requires the exact name; standard delete uses a normal confirm.
- First message updates the sidebar title; rename updates sidebar, header, and Home.

### 8.4 Visual coverage

Add `docs/reviews/2026-11-21-ux-4/` with deterministic captures for:

- 404 page;
- session not found;
- list/section error state;
- form validation;
- standard confirmation;
- type-to-confirm dialog;
- titled and renamed session in the sidebar/header.

## 9. Migration and compatibility

- The session title migration is additive and nullable.
- Existing sessions render fallback labels until renamed or given a first message.
- Existing API clients are unaffected; the new PATCH route is additive.
- Existing relative project paths continue to work and remain stored as supplied.
- Existing provider/agent/session behavior is preserved outside validation and confirmation.

## 10. Risks and trade-offs

- **Retry policy:** one retry for 5xx reduces transient noise but does not mask persistent outages.
- **Type-to-confirm friction:** limited to high-impact resources to avoid making routine cleanup painful.
- **Server validation:** path checks depend on the server filesystem; the UI message must describe that paths are validated on the server.
- **Session title truncation:** deterministic snippets may be imperfect but avoid model cost and latency.
- **Logging helper:** traceback text is slightly less structured than a live exception object but remains safe for enqueue and preserves diagnostics.

## 11. Acceptance criteria

- No failed list or detail request renders a successful empty state.
- Unknown routes and invalid sessions have explicit, navigable states.
- Blank names, invalid paths, and missing required selections are rejected in UI and API.
- All destructive actions use the chosen confirmation tier.
- Sessions receive a useful title on first message and can be renamed.
- Core permission descriptions are visible without a database backfill.
- Provider/MCP exceptions are visible in logs despite the async sink.
- Frontend, API, harness, models, and provider tests pass; E2E and Storybook builds pass.
