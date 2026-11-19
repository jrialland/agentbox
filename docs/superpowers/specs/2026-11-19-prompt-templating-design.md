# Prompt Templating — Design

Date: 2026-11-19
Status: Approved (design), spec awaiting review.

## Goal

Let agent authors use Jinja2 syntax in the system prompt (`instructions`),
render it with real session context before the agent is built, and test the
template in the agent form — including syntax errors, missing variables, and
the interpolated output.

## Decisions

- **Jinja2 `SandboxedEnvironment`**, `autoescape=False`, **no loader** (no
  `include`/`import`/`extends`).
- **Lenient undefined** (`ChainableUndefined`): missing variables render as
  empty strings. The preview reports them as warnings.
- **Syntax errors fail the run** with a clear `PromptTemplateError`; chat
  returns 422, ACP/A2A surface an error.
- Rendering happens in `prepare_agent`, **before** the skill catalog is
  appended by `augment_spec`.
- The stored `Agent.instructions` remains the raw template; `GET /agents`
  returns the raw text.

## Context schema

Same shape at runtime and in preview:

```python
{
    "agent": {"name": str, "description": str},
    "project": {"name": str, "path": str},
    "user": {"username": str},
    "session": {"id": str, "mode": str},
    "model": {"name": str, "provider": str},
    "skills": [{"name": str, "description": str}],
    "workspace": str,
    "date": str,       # YYYY-MM-DD
    "time": str,       # HH:MM:SS
    "datetime": str,   # ISO 8601
    "weekday": str,    # e.g. Wednesday
}
```

## Templating module

`packages/agentbox-api/src/agentbox_api/templating.py`:

- `ENV = SandboxedEnvironment(undefined=ChainableUndefined, autoescape=False)`
- `PromptTemplateError(Exception)` — carries `agent`, `message`, `line`.
- `render_prompt(template: str, context: dict, *, agent: str | None = None) -> str`
  — raises `PromptTemplateError` on `TemplateError` (syntax or sandbox).
- `preview_prompt(template: str, overrides: dict[str, str]) -> dict`:
  - builds the nested context from defaults merged with flat overrides;
  - parses with `ENV.parse` (catches syntax errors, keeping `lineno`);
  - computes missing top-level names with
    `jinja2.meta.find_undeclared_variables(parsed)`;
  - renders leniently; `TemplateError` during parse or render becomes the
    `error` object (`message`, `line` when available).
- `PREVIEW_CONTEXT: dict[str, str]` — flat sample values for every path
  (`agent.name`, `project.path`, `skills`, …); `skills` is a comma-separated
  string in the flat form.

## Runtime integration

`prepare_agent(factory, agent_name, project_root, user_dir, *, user_name=None,
session_id=None, session_mode=None, media_max_dimension=1568,
media_max_bytes=1_500_000)`:

1. `runtime = await resolve_agent_runtime(...)`.
2. `skills = discover_skills(...)`.
3. Build the context:
   - `agent` from `runtime.spec`, `project` from `project_root` (basename +
     path), `model` from `runtime.spec.model_binding`.
   - `user.username` = `user_name`, else the username of
     `runtime.created_by` (owner), else `""`.
   - `session` from the passed id/mode (empty when unknown).
   - `workspace = project_root`; date/time from `datetime.now(UTC)`.
4. `rendered = render_prompt(runtime.spec.instructions, context, agent=agent_name)`.
5. `spec = runtime.spec.model_copy(update={"instructions": rendered})`, then
   `augment_spec(spec, skills)` (catalog appended after rendering).
6. Log a warning when `find_undeclared_variables` reports variables absent
   from the context (still renders empty).

Call sites:

- `routers/sessions.py`: `user_name=request.user.username`,
  `session_id=sid`, `session_mode=body.mode or "agent"`.
- `acp_server.py`: `session_id=session_id`, `session_mode="agent"` (owner
  username fallback); `_restore` uses the existing session id.
- `a2a_executor.py`: `session_id=session_id`, `session_mode="agent"`.

Chat catches `PromptTemplateError` and raises
`HTTPException(status_code=422, detail=...)`.

## Preview API

`packages/agentbox-api/src/agentbox_api/routers/prompts.py`:

- `POST /prompts/preview`, permission `agents:create`.
- Body: `{ "template": str, "context": dict[str, str] = {} }`.
- Response (always 200):

```json
{
  "rendered": "...",
  "missing": ["user.username"],
  "error": {"message": "unexpected '}'", "line": 3},
  "context": {"agent.name": "...", "...": "..."},
  "variables": ["agent.name", "...", "skills"]
}
```

`error` is `null` on success; `context` is the merged flat context (defaults +
overrides) so the modal can populate its fields.

## UI

`AgentsPage`:

- A “Test template” button next to the Instructions textarea opens
  `TemplatePreviewModal`.
- Modal state: template (seeded from the form), flat context (seeded from the
  preview response), rendered output, errors/warnings.
- Fields: one `TextInput` per variable path; `skills` is comma-separated
  names. Date/time fields are editable text.
- “Render” calls `POST /prompts/preview` with the current template/context and
  shows the output; syntax errors render a red alert with the line, missing
  variables a yellow warning.
- “Apply to instructions” sets the form's `instructions` to the template and
  closes.
- New `previewPrompt` endpoint function + `usePreviewPrompt` mutation.

## Tests

- `test_templating.py`: interpolation, filters/loops, missing variable →
  empty + listed, syntax error line, sandbox rejects unsafe attribute access.
- `test_prompts_api.py`: success, missing variables, syntax error, permission.
- `test_prompt_rendering.py`: `prepare_agent` renders the prompt before the
  skill catalog and raises for invalid syntax; chat returns 422.
- E2E: open the modal, render `Hello {{ user.username }}`, see `Hello alice`,
  apply, and create the agent.

## Out of scope

- Editing existing agents (no edit form yet).
- Template includes/inheritance, autoescaping, and environment/os variables.
- Template syntax highlighting.
