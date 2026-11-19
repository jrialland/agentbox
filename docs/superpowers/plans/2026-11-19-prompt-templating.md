# Prompt Templating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render Jinja2 templates in agent instructions with session context, and add a preview API + agent-form modal that shows syntax errors, missing variables, and interpolated output.

**Architecture:** A `templating.py` module (sandboxed Jinja2, lenient undefined) builds context and renders. `prepare_agent` renders the raw instructions before `augment_spec`. `POST /prompts/preview` powers a modal in `AgentsPage`.

**Tech Stack:** Python 3.12, Jinja2, FastAPI, SQLModel, pytest; React/TypeScript, Mantine, react-query, Playwright.

## Global Constraints

- Engine: `SandboxedEnvironment(undefined=ChainableUndefined, autoescape=False)`, no loader.
- Missing variables render empty; preview lists them. Syntax errors are errors; chat returns 422.
- Render before `augment_spec`; stored instructions stay raw.
- Context keys: `agent{name,description}`, `project{name,path}`, `user{username}`, `session{id,mode}`, `model{name,provider}`, `skills[{name,description}]`, `workspace`, `date`, `time`, `datetime`, `weekday`.
- Regenerate `apps/web/openapi.json` + `schema.d.ts` after API changes.
- Run `ruff`/`ty` and the relevant test suites before each commit.

---

### Task 1: Templating module

**Files:**
- Modify: `packages/agentbox-api/pyproject.toml`
- Create: `packages/agentbox-api/src/agentbox_api/templating.py`
- Test: `packages/agentbox-api/tests/test_templating.py`

**Interfaces:**
- Produces: `PromptTemplateError`, `build_context(...)`, `render_prompt(template, context, *, agent=None)`, `preview_prompt(template, overrides=None)`, `PREVIEW_CONTEXT`.

- [ ] **Step 1: Add Jinja2**

Add `"jinja2>=3.1",` to the API dependencies and run `uv sync`.

- [ ] **Step 2: Write failing tests**

```python
from agentbox_api.templating import build_context, preview_prompt, render_prompt


def test_render_interpolates_and_filters():
    ctx = {"user": {"username": "Alice"}, "skills": [{"name": "a", "description": ""}]}
    assert render_prompt("Hi {{ user.username|lower }}", ctx) == "hi alice"
    assert render_prompt("{% for s in skills %}{{ s.name }}{% endfor %}", ctx) == "a"


def test_preview_reports_missing_variables():
    out = preview_prompt("Hello {{ user.username }} {{ nope }}")
    assert out["rendered"] == "Hello alice "
    assert out["missing"] == ["nope"]
    assert out["error"] is None
    assert out["context"]["user.username"] == "alice"


def test_preview_syntax_error_has_line():
    out = preview_prompt("line1\n{% if %}")
    assert out["rendered"] == ""
    assert out["error"]["line"] == 2


def test_preview_sandbox_blocks_unsafe_access():
    out = preview_prompt("{{ ''.__class__.__mro__ }}")
    assert out["error"] is not None


def test_build_context_uses_now():
    from datetime import UTC, datetime

    ctx = build_context(
        agent_name="a",
        agent_description="",
        project_root="proj",
        user_name="bob",
        session_id="s",
        session_mode="agent",
        model_name="m",
        model_provider="p",
        skills=[],
        now=datetime(2026, 11, 19, 12, 0, tzinfo=UTC),
    )
    assert ctx["date"] == "2026-11-19"
    assert ctx["time"] == "12:00:00"
    assert ctx["project"]["path"] == "proj"
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest packages/agentbox-api/tests/test_templating.py -q`
Expected: `ModuleNotFoundError`.

- [ ] **Step 4: Implement**

Create `templating.py`:

```python
import pathlib
from datetime import UTC, datetime

from jinja2 import ChainableUndefined, TemplateError, meta
from jinja2.sandbox import SandboxedEnvironment
from loguru import logger

ENV = SandboxedEnvironment(undefined=ChainableUndefined, autoescape=False)

PREVIEW_CONTEXT: dict[str, str] = {
    "agent.name": "my-agent",
    "agent.description": "A helpful assistant",
    "project.name": "my-project",
    "project.path": "/path/to/project",
    "user.username": "alice",
    "session.id": "session-123",
    "session.mode": "agent",
    "model.name": "gpt-4o",
    "model.provider": "openai",
    "skills": "commit-message, code-review",
    "workspace": "/path/to/project",
    "date": "2026-11-19",
    "time": "12:00:00",
    "datetime": "2026-11-19T12:00:00+00:00",
    "weekday": "Thursday",
}

VARIABLES = list(PREVIEW_CONTEXT)


class PromptTemplateError(Exception):
    def __init__(self, message, *, agent=None, line=None):
        super().__init__(message)
        self.message = message
        self.agent = agent
        self.line = line


def _flat_to_context(flat: dict[str, str]) -> dict:
    skills = [
        {"name": part.strip(), "description": ""}
        for part in flat["skills"].split(",")
        if part.strip()
    ]
    return {
        "agent": {
            "name": flat["agent.name"],
            "description": flat["agent.description"],
        },
        "project": {"name": flat["project.name"], "path": flat["project.path"]},
        "user": {"username": flat["user.username"]},
        "session": {"id": flat["session.id"], "mode": flat["session.mode"]},
        "model": {"name": flat["model.name"], "provider": flat["model.provider"]},
        "skills": skills,
        "workspace": flat["workspace"],
        "date": flat["date"],
        "time": flat["time"],
        "datetime": flat["datetime"],
        "weekday": flat["weekday"],
    }


def build_context(
    *,
    agent_name: str,
    agent_description: str,
    project_root: str,
    user_name: str | None,
    session_id: str | None,
    session_mode: str | None,
    model_name: str,
    model_provider: str,
    skills,
    now: datetime | None = None,
) -> dict:
    moment = now or datetime.now(UTC)
    return {
        "agent": {"name": agent_name, "description": agent_description},
        "project": {
            "name": pathlib.Path(project_root).name or str(project_root),
            "path": str(project_root),
        },
        "user": {"username": user_name or ""},
        "session": {"id": session_id or "", "mode": session_mode or ""},
        "model": {"name": model_name, "provider": model_provider},
        "skills": [
            {"name": skill.name, "description": skill.description} for skill in skills
        ],
        "workspace": str(project_root),
        "date": moment.date().isoformat(),
        "time": moment.strftime("%H:%M:%S"),
        "datetime": moment.isoformat(),
        "weekday": moment.strftime("%A"),
    }


def _missing(template: str, context: dict) -> list[str]:
    parsed = ENV.parse(template)
    return sorted(
        name for name in meta.find_undeclared_variables(parsed) if name not in context
    )


def render_prompt(template: str, context: dict, *, agent: str | None = None) -> str:
    try:
        missing = _missing(template, context)
        if missing:
            logger.warning(
                "prompt template missing variables agent={} vars={}", agent, missing
            )
        return ENV.from_string(template).render(**context)
    except TemplateError as exc:
        raise PromptTemplateError(
            str(exc), agent=agent, line=getattr(exc, "lineno", None)
        ) from exc


def preview_prompt(template: str, overrides: dict[str, str] | None = None) -> dict:
    flat = dict(PREVIEW_CONTEXT)
    flat.update({key: value for key, value in (overrides or {}).items() if key in flat})
    context = _flat_to_context(flat)
    try:
        missing = _missing(template, context)
        rendered = ENV.from_string(template).render(**context)
        error = None
    except TemplateError as exc:
        missing = []
        rendered = ""
        error = {"message": str(exc), "line": getattr(exc, "lineno", None)}
    return {
        "rendered": rendered,
        "missing": missing,
        "error": error,
        "context": flat,
        "variables": VARIABLES,
    }
```

- [ ] **Step 5: Run tests and commit**

```bash
uv run pytest packages/agentbox-api/tests/test_templating.py -q
git add packages/agentbox-api/pyproject.toml uv.lock packages/agentbox-api/src/agentbox_api/templating.py packages/agentbox-api/tests/test_templating.py
git commit -m "feat(api): add sandboxed prompt templating"
```

---

### Task 2: Render in `prepare_agent` and fail clearly

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/skills.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`
- Modify: `packages/agentbox-api/src/agentbox_api/acp_server.py`
- Modify: `packages/agentbox-api/src/agentbox_api/a2a_executor.py`
- Test: create `packages/agentbox-api/tests/test_prompt_rendering.py`

**Interfaces:**
- Consumes: `build_context`, `render_prompt`, `PromptTemplateError`.
- Produces: `prepare_agent(..., user_name=None, session_id=None, session_mode=None)` with rendered instructions.

- [ ] **Step 1: Write failing tests**

```python
import httpx
from sqlmodel import select

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_api.skills import prepare_agent
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import (
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)
from agentbox_models.tables.core import Agent, Model, Provider


async def _setup(instructions: str):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            User(
                id="u1",
                username="alice",
                email="a@x",
                password_hash=hash_password("pw"),
            )
        )
        s.add(Role(id="r1", name="role"))
        for i, permission in enumerate(
            ("sessions:create", "sessions:read", "agents:create", "agents:read", "projects:create")
        ):
            s.add(Permission(id=f"p{i}", name=permission))
            s.add(RolePermissionLink(role_id="r1", permission_id=f"p{i}"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(Provider(id="prov", name="prov", kind="test"))
        s.add(Model(id="m1", provider_id="prov", name="test-model"))
        s.add(
            Agent(
                id="ag",
                name="bot",
                description="d",
                instructions=instructions,
                model_id="m1",
            )
        )
        await s.commit()
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    return engine, client, factory


async def _auth(client) -> dict:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_prepare_agent_renders_before_skill_catalog(tmp_path):
    engine, _, factory = await _setup("Hello {{ user.username }}")
    try:
        prepared = await prepare_agent(
            factory, "bot", str(tmp_path), str(tmp_path / "skills"), user_name="alice"
        )
        assert prepared.spec.instructions.startswith("Hello alice")
    finally:
        await engine.dispose()


async def test_chat_rejects_broken_template():
    engine, client, _ = await _setup("{% if %}")
    try:
        h = await _auth(client)
        project = await client.post(
            "/projects", json={"name": "p", "path": "."}, headers=h
        )
        session = await client.post(
            "/sessions",
            json={"project_id": project.json()["id"], "agent_id": "bot"},
            headers=h,
        )
        r = await client.post(
            f"/sessions/{session.json()['id']}/messages",
            json={"content": "hi", "mode": "agent"},
            headers=h,
        )
        assert r.status_code == 422
        assert "prompt" in r.json()["detail"].lower() or "unexpected" in r.json()["detail"].lower()
    finally:
        await client.aclose()
        await engine.dispose()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/agentbox-api/tests/test_prompt_rendering.py -q`
Expected: FAIL (instructions unrendered / 200 instead of 422).

- [ ] **Step 3: Implement**

In `skills.py`, import `PromptTemplateError` (re-export), `build_context`, `render_prompt`, and `User`:

```python
from agentbox_api.templating import PromptTemplateError, build_context, render_prompt
from agentbox_models.tables.auth import User
```

Change the signature and body:

```python
async def prepare_agent(
    factory,
    agent_name: str,
    project_root: str,
    user_dir: str,
    user_name: str | None = None,
    session_id: str | None = None,
    session_mode: str | None = None,
    media_max_dimension: int = 1568,
    media_max_bytes: int = 1_500_000,
) -> PreparedAgent:
    runtime = await resolve_agent_runtime(factory, agent_name)
    skills = discover_skills(project_root, user_dir)
    resolved_user = user_name
    if resolved_user is None and runtime.created_by:
        async with factory() as s:
            owner = await s.get(User, runtime.created_by)
            resolved_user = owner.username if owner else None
    context = build_context(
        agent_name=runtime.spec.name,
        agent_description=runtime.spec.description,
        project_root=project_root,
        user_name=resolved_user,
        session_id=session_id,
        session_mode=session_mode,
        model_name=runtime.spec.model_binding.model,
        model_provider=runtime.spec.model_binding.provider,
        skills=skills,
    )
    rendered = render_prompt(runtime.spec.instructions, context, agent=agent_name)
    spec = runtime.spec.model_copy(update={"instructions": rendered})
    spec = augment_spec(spec, skills)
    extra_tools = {"activate_skill": make_activate_tool(skills)} if skills else None
    registry = build_registry(
        project_root,
        extra_read_roots=[s.location.parent for s in skills],
        extra_tools=extra_tools,
        media_max_dimension=media_max_dimension,
        media_max_bytes=media_max_bytes,
    )
    return PreparedAgent(runtime, spec, registry, skills)
```

In `routers/sessions.py`, wrap the `prepare_agent` call:

```python
    try:
        prepared = await prepare_agent(
            factory,
            agent.name,
            project.path,
            request.app.state.settings.skills_user_dir,
            user_name=getattr(request.user, "username", None),
            session_id=sid,
            session_mode=body.mode or "agent",
            media_max_dimension=request.app.state.settings.media_max_dimension,
            media_max_bytes=request.app.state.settings.media_max_bytes,
        )
    except PromptTemplateError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
```

Import `PromptTemplateError` in `sessions.py`.

In `acp_server.py` `new_session` and `_restore`, add `session_id=...` and `session_mode="agent"`:

```python
        prepared = await prepare_agent(
            self._factory,
            self._agent_name,
            cwd,
            self._settings.skills_user_dir,
            session_id=session_id,
            session_mode="agent",
            media_max_dimension=self._settings.media_max_dimension,
            media_max_bytes=self._settings.media_max_bytes,
        )
```

For `_restore`, use the existing `session_id` variable and `session_mode="agent"` (mirror the same keyword arguments).

In `a2a_executor.py`, add `session_id=session_id, session_mode="agent"` to the call.

- [ ] **Step 4: Run tests and commit**

```bash
uv run pytest packages/agentbox-api/tests/test_prompt_rendering.py -q
uv run pytest packages/agentbox-api/tests/test_chat.py packages/agentbox-api/tests/test_acp.py packages/agentbox-api/tests/test_a2a.py -q
git add packages/agentbox-api/src/agentbox_api/skills.py packages/agentbox-api/src/agentbox_api/routers/sessions.py packages/agentbox-api/src/agentbox_api/acp_server.py packages/agentbox-api/src/agentbox_api/a2a_executor.py packages/agentbox-api/tests/test_prompt_rendering.py
git commit -m "feat(api): render agent prompts with session context"
```

---

### Task 3: Preview endpoint

**Files:**
- Create: `packages/agentbox-api/src/agentbox_api/routers/prompts.py`
- Modify: `packages/agentbox-api/src/agentbox_api/app.py`
- Test: create `packages/agentbox-api/tests/test_prompts_api.py`

**Interfaces:**
- Consumes: `preview_prompt`.
- Produces: `POST /prompts/preview`.

- [ ] **Step 1: Write failing test**

```python
import httpx

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import (
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)


async def _client():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw")))
        s.add(Role(id="r1", name="role"))
        s.add(Permission(id="p0", name="agents:create"))
        s.add(RolePermissionLink(role_id="r1", permission_id="p0"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        await s.commit()
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return engine, client


async def test_preview_returns_rendered_and_context():
    engine, client = await _client()
    try:
        r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        r = await client.post(
            "/prompts/preview",
            json={"template": "Hi {{ user.username }}", "context": {"user.username": "bob"}},
            headers=h,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["rendered"] == "Hi bob"
        assert body["error"] is None
        assert body["context"]["user.username"] == "bob"
        assert "project.path" in body["variables"]
    finally:
        await client.aclose()
        await engine.dispose()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/agentbox-api/tests/test_prompts_api.py -q`
Expected: 404.

- [ ] **Step 3: Implement**

Create `routers/prompts.py`:

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agentbox_api.deps import require_permission
from agentbox_api.templating import preview_prompt

router = APIRouter(prefix="/prompts", tags=["prompts"])


class PreviewRequest(BaseModel):
    template: str
    context: dict[str, str] = {}


@router.post("/preview")
async def preview(
    body: PreviewRequest, _=Depends(require_permission("agents:create"))
):
    return preview_prompt(body.template, body.context)
```

In `app.py`, import `from agentbox_api.routers.prompts import router as prompts_router` and `app.include_router(prompts_router)`.

- [ ] **Step 4: Run tests and commit**

```bash
uv run pytest packages/agentbox-api/tests/test_prompts_api.py -q
git add packages/agentbox-api/src/agentbox_api/routers/prompts.py packages/agentbox-api/src/agentbox_api/app.py packages/agentbox-api/tests/test_prompts_api.py
git commit -m "feat(api): prompt preview endpoint"
```

---

### Task 4: Web client and types

**Files:**
- Regenerate: `apps/web/openapi.json`, `apps/web/src/api/schema.d.ts`
- Modify: `apps/web/src/api/endpoints.ts`
- Modify: `apps/web/src/api/queries.ts`

- [ ] **Step 1: Regenerate**

```bash
uv run python apps/web/scripts/gen-openapi.py
cd apps/web && bun run codegen
```

- [ ] **Step 2: Add the client**

In `endpoints.ts`:

```ts
export type PromptPreview = {
  rendered: string;
  missing: string[];
  error: { message: string; line?: number | null } | null;
  context: Record<string, string>;
  variables: string[];
};

export async function previewPrompt(body: {
  template: string;
  context: Record<string, string>;
}): Promise<PromptPreview> {
  const { data, error } = await api.POST("/prompts/preview", { body });
  if (error) throw new Error("Failed to preview prompt");
  return data as PromptPreview;
}
```

In `queries.ts`, import `previewPrompt` and add:

```ts
export function usePreviewPrompt() {
  return useMutation({ mutationFn: previewPrompt });
}
```

- [ ] **Step 3: Typecheck and commit**

```bash
cd apps/web && bun run build
git add apps/web/openapi.json apps/web/src/api/schema.d.ts apps/web/src/api/endpoints.ts apps/web/src/api/queries.ts
git commit -m "feat(web): prompt preview client"
```

---

### Task 5: Test-template modal + E2E

**Files:**
- Modify: `apps/web/src/pages/AgentsPage.tsx`
- Modify: `apps/web/e2e/management.spec.ts` (or `provider-model-admin.spec.ts`)

**Interfaces:**
- Consumes: `usePreviewPrompt`.

- [ ] **Step 1: Implement the modal**

In `AgentsPage.tsx`, import `usePreviewPrompt`, add a “Test template” button beside the Instructions `Textarea`, and a modal component:

```tsx
function TemplatePreviewModal({
  initialTemplate,
  onApply,
  onClose,
}: {
  initialTemplate: string;
  onApply: (template: string) => void;
  onClose: () => void;
}) {
  const preview = usePreviewPrompt();
  const [template, setTemplate] = useState(initialTemplate);
  const [context, setContext] = useState<Record<string, string>>({});
  const [result, setResult] = useState<{
    rendered: string;
    missing: string[];
    error: { message: string; line?: number | null } | null;
    variables: string[];
  } | null>(null);

  async function renderNow() {
    const data = await preview.mutateAsync({ template, context });
    setContext(data.context);
    setResult(data);
  }

  return (
    <Modal opened onClose={onClose} title="Test prompt template" size="xl">
      <Textarea label="Template" minRows={6} value={template}
        onChange={(e) => setTemplate(e.currentTarget.value)} />
      <Button mt="sm" onClick={renderNow} loading={preview.isPending}>Render</Button>
      {result && (
        <>
          {result.error && (
            <div role="alert" style={{ color: "red" }}>
              {result.error.message}
              {result.error.line ? ` (line ${result.error.line})` : ""}
            </div>
          )}
          {result.missing.length > 0 && (
            <div role="status" style={{ color: "orange" }}>
              Missing: {result.missing.join(", ")}
            </div>
          )}
          <Textarea label="Rendered" minRows={6} readOnly value={result.rendered} />
          {(result.variables ?? []).map((path) => (
            <TextInput
              key={path}
              label={path}
              value={context[path] ?? ""}
              onChange={(e) => {
                const value = e.currentTarget.value;
                setContext((prev) => ({ ...prev, [path]: value }));
              }}
            />
          ))}
        </>
      )}
      <Button mt="md" onClick={() => { onApply(template); onClose(); }}>
        Apply to instructions
      </Button>
    </Modal>
  );
}
```

In `AgentsPage`, add `const [previewOpen, setPreviewOpen] = useState(false);`, a button `<Button variant="light" onClick={() => setPreviewOpen(true)}>Test template</Button>` next to Instructions, and render:

```tsx
{previewOpen && (
  <TemplatePreviewModal
    initialTemplate={instructions}
    onApply={setInstructions}
    onClose={() => setPreviewOpen(false)}
  />
)}
```

- [ ] **Step 2: E2E**

In `management.spec.ts`, after opening Agents, fill Name, set Instructions to `Hello {{ user.username }}`, click “Test template”, click “Render”, assert the “Rendered” textarea has value `Hello alice`, click “Apply to instructions”, and assert the Instructions textarea contains the template.

- [ ] **Step 3: Run and commit**

```bash
cd apps/web && bun run build && bun run e2e -- management.spec.ts
git add apps/web/src/pages/AgentsPage.tsx apps/web/e2e/management.spec.ts
git commit -m "feat(web): test prompt templates in the agent form"
```

---

### Task 6: Roadmap and full verification

**Files:**
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Update the roadmap**

Remove the D2 row from the deferred backlog and add:

```markdown
| 23 | Prompt templating in system prompts + preview | `specs/2026-11-19-prompt-templating-design.md` | `plans/2026-11-19-prompt-templating.md` |
```

- [ ] **Step 2: Verify**

```bash
uv run ruff check --fix packages
uv run ty check packages
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-api -q
cd apps/web && bun run test && bun run build
```

- [ ] **Step 3: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs(roadmap): prompt templating complete"
```
