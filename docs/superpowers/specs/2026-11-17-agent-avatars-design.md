# Agent Avatars (RoboHash default + custom photo) — Design Specification

- **Date:** 2026-11-17
- **Status:** Draft (brainstormed, pending implementation plan)
- **Sub-project:** Agents — a default avatar generated with **RoboHash set #1**, plus the ability to upload a custom photo ("profile photo") and reset back to the default.

## 1. Context and Scope

The initial spec requires:
- "it is also possible to attach a photograph to an agent. By default, this photograph is generated from the Python library **RoboHash** or an equivalent." (`initial_spec.md:51`)
- "the system for managing agent avatar photos be complete, notably the use of **RoboHash** by default. The images must come from **RoboHash set number 1**. It is not permitted to reproduce or imagine any other system than this one." (`initial_spec.md:118`)

The `Agent.avatar_url` column exists (`agentbox_models/tables/core.py`) but there is no generation, upload, or UI.

### 1.1 What this sub-project encompasses
- Default avatar generation from **RoboHash set1** (local, via the `robohash` Python library).
- Custom photo upload (normalized to a square 300×300 PNG) and reset to the default.
- Avatars shown in agent management (create + list rows) and the session chat header.
- Required RoboHash/CC attribution as `NOTICE` + README (no in-app attribution, per decision).

### 1.2 Boundaries
- Avatars are for **agents** only (not users) — user avatars stay future work.
- No agent-edit page is added; upload happens on create and per-row, not via a full edit form.
- No external network: generation uses the local `robohash` library; images never leave the backend.

### 1.3 Dependencies
- `agentbox-api`, `agentbox-models`, `apps/web`; new Python dep `robohash` (pulls `pillow`, `natsort`).

## 2. Decisions and Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Generate defaults locally with the `robohash` PyPI library, `roboset='set1'`. | Matches the spec's "Python library RoboHash"; deterministic; no external service. |
| D2 | Seed = the agent **id** (stable across renames). | Renaming an agent must not change its default avatar. |
| D3 | `GET /agents/{name}/avatar` is **public** (no auth). | The browser loads it as `<img src>`, which cannot carry the Bearer token; avatars are non-sensitive. |
| D4 | Custom uploads are normalized with Pillow: center-crop square, 300×300, PNG, metadata stripped. | Consistent avatars, small storage, no EXIF leak. |
| D5 | Custom bytes stored as a DB blob (`agents.avatar_data`), like session attachments. | Consistency with existing blob storage; no filesystem management. |
| D6 | RoboHash is only the default; a user may upload any png/jpeg/webp (≤2 MB). | The spec requires an attachable photograph, not a fixed image. |
| D7 | Attribution in `NOTICE` + README only (no in-app). | User choice. |
| D8 | Avatars shown in agent management + the chat header. | User choice. |

## 3. Backend

### 3.1 Schema
Add to `Agent` (`agentbox_models/tables/core.py`):
- `avatar_data: bytes | None` (LargeBinary)
- `avatar_media_type: str | None`

Alembic migration adds both nullable columns. `avatar_url` stays unused (legacy).

### 3.2 Avatar service (`agentbox_api/avatars.py`)
- `generate_default_avatar(seed: str, size: int = 300) -> bytes`:
  ```python
  rh = Robohash(seed)
  rh.assemble(roboset="set1", sizex=size, sizey=size, format="png")
  buf = io.BytesIO(); rh.img.save(buf, format="PNG"); return buf.getvalue()
  ```
  Memoized in an in-process LRU (`functools.lru_cache`/dict) keyed by `(seed, size)`.
- `normalize_upload(data: bytes) -> bytes`:
  - Open with Pillow (catch `UnidentifiedImageError` → raise a validation error).
  - Convert to RGB, center-crop to the largest centered square, `resize((300,300), LANCZOS)`.
  - Save PNG (re-encode strips metadata) into bytes.
- Constants: `MAX_UPLOAD_BYTES = 2 * 1024 * 1024`, `ALLOWED_UPLOAD_TYPES = {"image/png","image/jpeg","image/webp"}`, `AVATAR_SIZE = 300`.

### 3.3 Endpoints (`routers/agents.py`)
- `GET /agents/{name}/avatar` (public; no `require_permission`):
  - 404 if the agent does not exist.
  - Custom set → `Response(content=avatar_data, media_type=avatar_media_type)`.
  - Else → `Response(generate_default_avatar(agent.id), media_type="image/png")`.
  - Headers: `Cache-Control: no-cache` + `ETag` (hash of the bytes); honour `If-None-Match` → 304.
- `PUT /agents/{name}/avatar` (auth, `agents:create` — there is no `agents:update` permission yet):
  - Validate `UploadFile.content_type ∈ ALLOWED_UPLOAD_TYPES` and size ≤ `MAX_UPLOAD_BYTES`.
  - `normalize_upload(bytes)` → store `avatar_data`, `avatar_media_type = "image/png"`; 204.
  - Invalid image → 415; too large → 413.
- `DELETE /agents/{name}/avatar` (auth, `agents:create`): clear both columns; 204 (no-op if none).

### 3.4 Session detail
- `GET /sessions/{sid}` returns a new `SessionDetail` model = `SessionRow` fields + `agent_name`, so the chat header can render the agent without a second lookup.

## 4. Frontend

### 4.1 `AgentAvatar` component
- Mantine `<Avatar src={`${API_URL}/agents/${encodeURIComponent(name)}/avatar?v=${version}`} name={name} radius="xl" />`.
- `version` prop (default `0`) is a cache-busting counter bumped after upload/reset.

### 4.2 Agents management (`AgentsPage`)
- Create form: a **Photo** file picker (optional). On successful create, if a file was chosen, `PUT /agents/{name}/avatar` then invalidate the agents query.
- Table: an avatar cell (`AgentAvatar`) per row; actions **Change photo** (hidden `<input type=file>` → PUT) and **Remove photo** (DELETE → default). Errors via Mantine notifications.

### 4.3 Chat header (`SessionPage`)
- Above the conversation: `AgentAvatar(agent_name)` + the agent name, from the new `useSession(id)` query.

### 4.4 Queries (`api/queries.ts`)
- `useSession(id)`, `useUploadAvatar()`, `useResetAvatar()`; invalidate `agents`, `session` after mutations.

## 5. Attribution

- `NOTICE` (repo root) and a README section:
  - RoboHash code: MIT/Expat, Copyright (c) 2011, https://github.com/e1ven/Robohash.
  - Set1 artwork: Zikri Kader, CC-BY-3.0 / CC-BY-4.0.
  - Suggested wording: "Robots lovingly delivered by Robohash.org".

## 6. Testing

- **Backend pytest**:
  - default avatar: 200, `image/png`, deterministic (two calls equal); 404 unknown agent.
  - upload: PNG bytes stored; `GET` returns the normalized 300×300 PNG; reset returns the default; invalid type → 415; oversized → 413.
- **Frontend Vitest**: `AgentAvatar` renders the expected `src`; upload mutation calls the endpoint; chat header shows the agent name/avatar.
- **E2E** (real stack): create an agent → its row shows an avatar `<img>`; upload a tiny PNG → the avatar `src` changes; remove → back to default; the session chat header shows the agent avatar/name.

## 7. Error Handling

- Invalid/oversized uploads → 415/413 with a notification in the UI.
- Missing agent → 404.
- Generation failure → 500 (logged); the UI shows a broken/fallback avatar (Mantine fallback initials via `name`).

## 8. Open Items / Future Work

- User avatars (only agents in scope).
- A dedicated `agents:update` permission (upload/reset currently reuse `agents:create`).
- Agent edit page (upload is create-time + per-row).
- Optional CDN/immutable caching for avatars in production.

## References

- Initial spec — `docs/initial_spec.md` (lines 51, 118).
- RoboHash — https://github.com/e1ven/Robohash (PyPI `robohash` 2.0, MIT; set1 art by Zikri Kader, CC-BY).
