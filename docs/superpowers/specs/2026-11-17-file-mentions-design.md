# `@` File Autocomplete — Design Specification

- **Date:** 2026-11-17
- **Status:** Draft (brainstormed; approved scope)
- **Sub-project:** Chat `@` autocomplete — cite a project file while prompting (e.g. `@packages/agentbox-api/src/agentbox_api/streaming.py`).

## 1. Context and Scope

The initial spec: "The `@` character autocompletes filenames relative to the project root." (`initial_spec.md:83`). The `/` skills menu already exists in the composer; this adds an analogous `@` file menu.

### 1.1 What this sub-project encompasses
- A session-scoped **project file listing** endpoint (bounded, query-filtered).
- Composer **`@` menu** that inserts `@relative/path` into the message.
- Path-only mentions; the agent reads the file with its existing filesystem tools.

### 1.2 Boundaries
- No automatic file-content attachment (deferred).
- No fuzzy ranking or directory-by-directory browsing; substring filter over a bounded list.
- `.gitignore` parsing is not used (fixed skip list instead).

## 2. Decisions and Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Selecting a file inserts `@relative/path` only; no content is auto-attached. | Matches the spec ("autocomplete filenames"); the agent has read tools. |
| D2 | `GET /sessions/{sid}/files?q=` (session-scoped) resolves the project from the session. | The composer already has the session id; project path is server-side. |
| D3 | Bounded recursive listing: skip `.git`, `node_modules`, `.venv`, `dist`, `build`, `__pycache__`, `.tox`, `.mypy_cache`, `.pytest_cache`; max depth 8, max 1000 files. | Prevents runaway scans on large repos. |
| D4 | Return project-relative POSIX paths, confined to the project root, no symlink following. | Portable, safe. |

## 3. Backend

### 3.1 Endpoint
`GET /sessions/{sid}/files?q=` (`sessions:read`):
- 404 unknown session.
- Resolve `Project.path` from the session; walk it with the skip list/bounds; collect files; filter by `q` (case-insensitive substring on the relative POSIX path); return `{"files": [relative_posix, ...]}` (sorted, ≤1000).
- `q` empty → the first bounded page (still bounded).

### 3.2 Safety
- Use `os.walk(..., followlinks=False)`; prune skipped dirs; skip files that resolve outside the project root.
- No file contents read; only names.

## 4. Frontend

### 4.1 `@` menu (mirror the `/` skills menu)
- Detect an `@` token: the last `@` in the input whose following text has no whitespace (until the end/cursor).
- Debounce (~150 ms) and query `useSessionFiles(sessionId, q)`.
- Show a menu of up to ~8 matches; selecting replaces the `@query` token with `@relative/path `.
- The menu and the `/` menu are mutually exclusive (show only when the corresponding trigger is active).

### 4.2 API layer
- `fetchSessionFiles(sid, q)` and `useSessionFiles(sid, q)` (enabled when `q` non-empty, `staleTime` short).

## 5. Testing

- **Backend pytest**: listing respects the skip list/bounds; filters by `q`; returns project-relative POSIX paths; rejects/ignores paths outside the project; 404 unknown session.
- **Frontend Vitest**: typing `@` + a query shows matches (mocked query); selecting inserts `@path ` into the input.
- **E2E**: in a session, type `@` + a known filename fragment, select it, assert the composer value ends with `@<relative path> `.

## 6. Error Handling

- 404 unknown session.
- Empty/mismatched query → empty menu (no error).
- Files outside the project → skipped.

## 7. Open Items / Future Work

- Auto-attach referenced file contents (like @-mentions) with size caps.
- Fuzzy ranking, `.gitignore` support, cursor-aware tokens.

## References

- Initial spec — `docs/initial_spec.md:83`.
- Existing code — `apps/web/src/chat/Composer.tsx` (the `/` menu), `apps/web/src/api/{endpoints,queries}.ts`, `routers/sessions.py`, `Project.path`.
