# `@` File Autocomplete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:executing-plans` (or `subagent-driven-development`). Steps use checkbox (`- [ ]`) syntax.

**Goal:** `@` in the chat composer autocompletes project-relative file paths and inserts `@relative/path` into the message.

**Architecture:** A session-scoped backend endpoint lists bounded, query-filtered project files; the composer shows a debounced `@` menu (mirroring the `/` skills menu) and replaces the `@query` token with `@path `.

**Tech Stack:** FastAPI, SQLModel, React 19, Mantine v9, TanStack Query, Playwright.

## Global Constraints

- Insert the **path only** (`@relative/path`); no content auto-attach.
- Listing is **bounded** (skip `.git`, `node_modules`, `.venv`, `dist`, `build`, `__pycache__`, `.tox`, `.mypy_cache`, `.pytest_cache`; max depth 8; ≤1000 files), project-confined, no symlink following.
- Relative POSIX paths.
- `ruff`/`ty`/`bandit` clean; existing tests keep passing.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `.../routers/sessions.py` | `GET /sessions/{sid}/files?q=` |
| `packages/agentbox-api/tests/test_files_listing.py` | listing tests |
| `apps/web/src/api/endpoints.ts`, `queries.ts` | `fetchSessionFiles`/`useSessionFiles` |
| `apps/web/src/chat/Composer.tsx` | `@` menu + token replacement |
| `apps/web/src/chat/Composer.test.tsx` | Vitest |
| `apps/web/e2e/file-mentions.spec.ts` | E2E |

---

### Task 1: Backend — session file listing

**Files:** `routers/sessions.py`; create `tests/test_files_listing.py`.

- [ ] **Step 1: Failing test**

```python
import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import Permission, Role, RolePermissionLink, User, UserRoleLink
from agentbox_models.tables.core import Agent, Model, Project, Provider, SessionRow


async def test_session_files_listing(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "streaming.py").write_text("x", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("x", encoding="utf-8")

    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw")))
        s.add(Role(id="r1", name="role"))
        s.add(Permission(id="p0", name="sessions:read"))
        s.add(RolePermissionLink(role_id="r1", permission_id="p0"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(Provider(id="prov", name="test", kind="test"))
        s.add(Model(id="m", provider_id="prov", name="test-model"))
        s.add(Agent(id="ag", name="a", description="", instructions="", model_id="m"))
        s.add(Project(id="prj", name="p", path=str(tmp_path), owner_id="u1"))
        s.add(SessionRow(id="s1", project_id="prj", agent_id="ag"))
        await s.commit()
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        token = (
            await client.post("/auth/login", json={"username": "alice", "password": "pw"})
        ).json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        r = await client.get("/sessions/s1/files?q=stream", headers=h)
        files = r.json()["files"]
        assert "pkg/streaming.py" in files
        assert all(not f.startswith("node_modules/") for f in files)
        assert (await client.get("/sessions/nope/files", headers=h)).status_code == 404
    finally:
        await client.aclose()
        await engine.dispose()
```

- [ ] **Step 2: Run to verify it fails** — `uv run pytest packages/agentbox-api/tests/test_files_listing.py -q`.

- [ ] **Step 3: Implement in `routers/sessions.py`**

```python
import os

_SKIP = {
    ".git", "node_modules", ".venv", "dist", "build", "__pycache__",
    ".tox", ".mypy_cache", ".pytest_cache",
}
_MAX_FILES = 1000
_MAX_DEPTH = 8


@router.get("/{sid}/files")
async def list_session_files(
    sid: str,
    request: Request,
    q: str = "",
    _=Depends(require_permission("sessions:read")),
):
    factory = request.app.state.session_factory
    async with factory() as s:
        row = (
            await s.execute(select(SessionRow).where(SessionRow.id == sid))
        ).scalars().first()
        if row is None:
            raise HTTPException(status_code=404, detail="Session not found")
        project = (
            await s.execute(select(Project).where(Project.id == row.project_id))
        ).scalars().first()
    root = pathlib.Path(project.path).resolve()
    ql = q.lower()
    results: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = pathlib.Path(dirpath).resolve().relative_to(root)
        if len(rel_dir.parts) >= _MAX_DEPTH:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d not in _SKIP]
        for name in filenames:
            try:
                rel = (
                    pathlib.Path(dirpath, name).resolve().relative_to(root).as_posix()
                )
            except ValueError:
                continue
            if ql and ql not in rel.lower():
                continue
            results.append(rel)
            if len(results) >= _MAX_FILES:
                return {"files": sorted(results)}
    return {"files": sorted(results)}
```
(Import `pathlib`, `os`.)

- [ ] **Step 4: Run + lint + commit**
```bash
uv run pytest packages/agentbox-api/tests/test_files_listing.py -q
uv run ruff check packages/agentbox-api
git add packages/agentbox-api/src/agentbox_api/routers/sessions.py packages/agentbox-api/tests/test_files_listing.py
git commit -m "feat(api): bounded session file listing for @ mentions"
```

---

### Task 2: Frontend — API + `@` menu

**Files:** `endpoints.ts`, `queries.ts`, `Composer.tsx`; create `Composer.test.tsx`; regen schema.

- [ ] **Step 1: Endpoints + hooks**

`endpoints.ts`:
```ts
export async function fetchSessionFiles(sid: string, q: string): Promise<string[]> {
  const { data } = await api.GET("/sessions/{sid}/files", {
    params: { path: { sid }, query: { q } },
  });
  return ((data as { files?: string[] })?.files) ?? [];
}
```
`queries.ts`:
```ts
export function useSessionFiles(sid: string, q: string) {
  return useQuery({
    queryKey: ["session-files", sid, q],
    queryFn: () => fetchSessionFiles(sid, q),
    enabled: q.length > 0,
    staleTime: 10_000,
  });
}
```

- [ ] **Step 2: Composer `@` menu**

In `Composer.tsx`, after the `/` skills logic:
```tsx
  const at = value.lastIndexOf("@");
  const atQuery = at >= 0 ? value.slice(at + 1) : null;
  const atActive = atQuery !== null && atQuery !== "" && !/\s/.test(atQuery);
  const { data: files } = useSessionFiles(sessionId, atActive ? atQuery : "");
  const fileMatches = atActive ? (files ?? []).slice(0, 8) : [];

  function pickFile(path: string) {
    if (at < 0) return;
    setValue(`${value.slice(0, at)}@${path} `);
  }
```
Render a menu (mirroring the skills menu) when `atActive && fileMatches.length > 0`:
```tsx
      {atActive && fileMatches.length > 0 && (
        <div className="box" data-testid="file-menu">
          {fileMatches.map((p) => (
            <button key={p} type="button" className="is-block" onClick={() => pickFile(p)}>
              @{p}
            </button>
          ))}
        </div>
      )}
```
Ensure the `/` and `@` menus don't both show (only one trigger active at a time; if `value.startsWith("/")` prefer the `/` menu).

- [ ] **Step 3: Vitest**

`Composer.test.tsx`:
```tsx
import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { vi } from "vitest";

vi.mock("../api/queries", () => ({
  useSkills: () => ({ data: [] }),
  useSessionFiles: (_sid: string, q: string) =>
    q ? { data: ["pkg/streaming.py"] } : { data: [] },
}));

import { Composer } from "./Composer";

function Harness() {
  const [value, setValue] = useState("@stream");
  return (
    <Composer
      sessionId="s1"
      value={value}
      setValue={setValue}
      mode="agent"
      setMode={() => {}}
      running={false}
      onSend={() => {}}
      onSelectSkill={() => {}}
    />
  );
}

test("inserts a cited file path", () => {
  render(<MantineProvider><Harness /></MantineProvider>);
  fireEvent.click(screen.getByRole("button", { name: "@pkg/streaming.py" }));
  expect(screen.getByLabelText("Message")).toHaveValue("@pkg/streaming.py ");
});
```

- [ ] **Step 4: Regen schema + build + commit**
```bash
uv run python -c "import json; from agentbox_api.app import create_app; from agentbox_api.config import Settings; open('apps/web/openapi.json','w',encoding='utf-8').write(json.dumps(create_app(Settings(jwt_secret='x'*32)).openapi(), indent=2))"
```
```powershell
Set-Location apps/web; bun run codegen; bun run test; bun run build
```
```bash
git add apps/web && git commit -m "feat(web): @ file autocomplete in the composer"
```

---

### Task 3: E2E

**Files:** `apps/web/e2e/file-mentions.spec.ts`.

- [ ] **Step 1: Spec** — login, create provider/agent/project/session via the API, open the session, type `@streaming.py`, assert the `file-menu` appears, select it, assert the composer value ends with `@<path> `.
- [ ] **Step 2: Run + commit**
```powershell
Set-Location apps/web; bun run e2e
```
```bash
git add apps/web/e2e/file-mentions.spec.ts && git commit -m "test(web): E2E @ file autocomplete"
```

---

## Notes

- The endpoint is session-scoped (resolves the project from the session); `q` empty returns a bounded page.
- Only one menu shows at a time; prefer `/` when the value starts with `/`.
- Content auto-attachment is future work.
