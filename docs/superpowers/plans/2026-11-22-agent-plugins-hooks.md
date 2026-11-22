# Agent Plugin Hooks (D12b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Status: Approved; implementation complete and verified.

**Goal:** Add declarative `com.agentbox/hooks/hooks.json` hooks that run on session, run, and tool events, with command/HTTP/context actions, allow/deny, argument mutation, result replacement, and request-context injection.

**Architecture:** A strict hook config model loaded by the plugin catalog, a command/HTTP executor, a pydantic-ai `PluginHooks` capability, and a process-scoped `PluginHookRuntime` for session lifecycle. Hooks follow plugin enablement and project scope; no database migration.

**Tech Stack:** Python 3.11+, pydantic-ai capabilities, FastAPI, React 19/Vite/Mantine, `httpx`, asyncio subprocesses.

## Global Constraints

- Python line length 100; Ruff target py311; first-party modules are `agentbox_*`.
- Do **not** commit unless the user explicitly asks.
- Hooks run only when their plugin is enabled; enabling is the trust action.
- No sandboxing in this cycle; commands run as the server user with timeouts,
  sanitized env, and path containment.
- No network schema retrieval, no Python code loading.
- Hook failures are fail-open by default; `on_error: deny` only affects
  `before_tool`.
- Hooks must never crash the run unless `on_error: deny` denies the call.
- Backend tests: one package per invocation.
- Checks: `uv run ruff check --fix packages`, `uv run ty check packages`.

---

### Task 1: Hook config models, catalog loading, and API summaries

**Files:**
- Create: `packages/agentbox-api/src/agentbox_api/plugin_hook_config.py`
- Modify: `packages/agentbox-api/src/agentbox_api/plugin_catalog.py`
- Modify: `packages/agentbox-api/src/agentbox_api/plugin_service.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/plugins.py`
- Test: `packages/agentbox-api/tests/test_plugin_hooks_config.py`

**Interfaces:**
- Produces: `HookEvent`, `HookAction`, `PluginHook`, `HookIssue` (or reuse `PluginIssue`).
- Produces: `load_plugin_hooks(root, data_root, issues) -> tuple[PluginHook, ...]`.
- Modifies: `LoadedPlugin.hooks`, `PluginView.hooks`.
- Modifies: plugin API serialization to include hook summaries.

- [ ] **Step 1: Write failing config/catalog tests**

```python
import json
import pathlib

from agentbox_api.plugin_catalog import PluginCatalog

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"


def _plugin_with_hooks(tmp_path, hooks):
    plugin = tmp_path / "user" / "acme-tools"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text(
        json.dumps({"$schema": PLUGIN_SCHEMA, "name": "acme-tools"}),
        encoding="utf-8",
    )
    hooks_dir = plugin / "com.agentbox" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "hooks.json").write_text(
        json.dumps({"version": 1, "hooks": hooks}),
        encoding="utf-8",
    )
    return plugin


def test_loads_valid_command_hook(tmp_path):
    _plugin_with_hooks(
        tmp_path,
        [
            {
                "id": "after-edit",
                "event": "after_tool",
                "tools": ["write_file"],
                "action": {
                    "type": "command",
                    "command": "./check.sh",
                    "timeout_ms": 1000,
                },
            }
        ],
    )
    loaded = PluginCatalog(
        str(tmp_path / "user"), str(tmp_path / "data")
    ).discover(str(tmp_path / "project"), "p1")[0]
    assert loaded.hooks[0].id == "after-edit"
    assert loaded.hooks[0].event == "after_tool"
    assert loaded.hooks[0].action.type == "command"


def test_invalid_hook_is_skipped_but_plugin_loads(tmp_path):
    _plugin_with_hooks(
        tmp_path,
        [
            {"id": "bad", "event": "after_tool", "action": {"type": "nope"}},
            {
                "id": "good",
                "event": "run_start",
                "action": {"type": "context", "text": "note"},
            },
        ],
    )
    loaded = PluginCatalog(
        str(tmp_path / "user"), str(tmp_path / "data")
    ).discover(str(tmp_path / "project"), "p1")[0]
    assert [hook.id for hook in loaded.hooks] == ["good"]
    assert any(
        issue.component.startswith("com.agentbox:hook:") for issue in loaded.issues
    )
```

Add tests for:

- all eight events;
- duplicate ids;
- unknown fields (`extra="forbid"`);
- `tools` rejected on non-tool events;
- invalid version/top-level;
- command/cwd path escape;
- invalid HTTP URL/header;
- timeout clamp;
- `on_error` values;
- invalid `hooks.json` disables hooks but keeps skills/MCP.

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-api/tests/test_plugin_hooks_config.py -q --timeout=60`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement the config models**

```python
HookEvent = Literal[
    "session_start",
    "session_end",
    "run_start",
    "run_end",
    "run_error",
    "before_tool",
    "after_tool",
    "tool_error",
]

TOOL_EVENTS = {"before_tool", "after_tool", "tool_error"}
MAX_HOOKS = 50
DEFAULT_TIMEOUT_MS = 5_000
MAX_TIMEOUT_MS = 30_000


class CommandAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["command"]
    command: str
    args: list[str] = []
    env: dict[str, str] = {}
    cwd: str = ""
    timeout_ms: int = DEFAULT_TIMEOUT_MS

    @field_validator("command")
    @classmethod
    def _command(cls, value):
        if not value.strip():
            raise ValueError("command is required")
        return value

    @field_validator("timeout_ms")
    @classmethod
    def _timeout(cls, value):
        return min(MAX_TIMEOUT_MS, max(100, value))


class HttpAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["http"]
    url: str
    method: str = "POST"
    headers: dict[str, str] = {}
    timeout_ms: int = DEFAULT_TIMEOUT_MS

    @field_validator("timeout_ms")
    @classmethod
    def _timeout(cls, value):
        return min(MAX_TIMEOUT_MS, max(100, value))


class ContextAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["context"]
    text: str


HookAction = Annotated[
    CommandAction | HttpAction | ContextAction,
    Field(discriminator="type"),
]


class PluginHook(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    event: HookEvent
    tools: list[str] = []
    action: HookAction
    on_error: Literal["ignore", "deny"] = "ignore"

    @model_validator(mode="after")
    def _matcher_scope(self):
        if self.tools and self.event not in TOOL_EVENTS:
            raise ValueError("tools is only valid for tool events")
        if self.on_error == "deny" and self.event != "before_tool":
            raise ValueError("on_error=deny is only valid for before_tool")
        return self
```

`load_plugin_hooks` reads `com.agentbox/hooks/hooks.json`, checks
`version == 1`, parses the closed top-level object, validates each hook, applies
path/URL/header checks (reuse D12a helpers), enforces unique ids and `MAX_HOOKS`,
and appends `PluginIssue` warnings for each skipped hook. A top-level invalid
file disables hooks for the plugin.

- [ ] **Step 4: Wire the catalog and views**

- Add `hooks: tuple[PluginHook, ...] = ()` to `LoadedPlugin`.
- If the manifest is valid, call `load_plugin_hooks(root, data_root, issues)` and
  store the result.
- Add `PluginView.hooks` delegating to `loaded.hooks`.
- Extend `routers/plugins._serialize` with:

```python
"hooks": [
    {
        "id": hook.id,
        "event": hook.event,
        "tools": list(hook.tools),
        "action": hook.action.type,
        "command": hook.action.command if hook.action.type == "command" else "",
        "url": hook.action.url if hook.action.type == "http" else "",
        "timeout_ms": getattr(hook.action, "timeout_ms", 0),
        "on_error": hook.on_error,
    }
    for hook in view.hooks
],
```

- [ ] **Step 5: Run config/catalog tests**

Run: `uv run pytest packages/agentbox-api/tests/test_plugin_hooks_config.py -q --timeout=60`
Expected: PASS.

---

### Task 2: Command/HTTP executor

**Files:**
- Create: `packages/agentbox-api/src/agentbox_api/plugin_hooks.py`
- Test: `packages/agentbox-api/tests/test_plugin_hooks_executor.py`

**Interfaces:**
- Produces: `HookContext`, `HookResult`, `HookExecutionError`.
- Produces: `HookExecutor.execute(hook, context) -> HookResult`.

- [ ] **Step 1: Write failing executor tests**

```python
async def test_command_hook_returns_context(tmp_path):
    script = tmp_path / "hook.py"
    script.write_text(
        "import json,sys; "
        "d=json.load(sys.stdin); "
        "print(json.dumps({'context': f\"seen {d['event']}\"}))",
        encoding="utf-8",
    )
    hook = PluginHook(
        id="note",
        event="run_start",
        action=CommandAction(
            type="command",
            command="python",
            args=[str(script)],
        ),
    )
    result = await HookExecutor().execute(
        hook,
        HookContext(event="run_start", session_id="s1"),
    )
    assert result.context == "seen run_start"


async def test_command_nonzero_is_hook_error(tmp_path):
    script = tmp_path / "hook.py"
    script.write_text("raise SystemExit(2)", encoding="utf-8")
    hook = PluginHook(...)
    with pytest.raises(HookExecutionError):
        await HookExecutor().execute(hook, HookContext(event="run_start"))
```

Add tests for plain-text output, malformed JSON, timeout kill, output cap,
env/cwd/placeholders, HTTP JSON/text/non-2xx/timeout/no redirects/response cap,
and static context.

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-api/tests/test_plugin_hooks_executor.py -q --timeout=60`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
@dataclass(frozen=True)
class HookContext:
    event: str
    session_id: str
    project_id: str | None = None
    project_root: str = ""
    run_id: str | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    args: dict | None = None
    result: Any = None
    error: dict | None = None
    plugin: str = ""
    hook_id: str = ""
    plugin_root: str = ""
    plugin_data: str = ""
    timestamp: str = ""


@dataclass(frozen=True)
class HookResult:
    decision: str | None = None
    reason: str = ""
    args: dict | None = None
    result: Any = None
    context: str = ""


class HookExecutionError(Exception): ...
```

Command runner:

- Resolve `command` relative to plugin root if it starts `./`; otherwise pass
  bare. Use `create_subprocess_exec` (no shell).
- Env: sanitized base env (`PATH`, `PATHEXT`, `SystemRoot`, `WINDIR`, `HOME`,
  `USERPROFILE`, `TEMP`, `TMP`), configured env after expansion, then
  `PLUGIN_ROOT`/`PLUGIN_DATA`/`AGENTBOX_*`.
- cwd: expand `./`, `${PLUGIN_ROOT}`, `${PLUGIN_DATA}`; default project root.
- Write JSON payload to stdin; close stdin.
- Read stdout/stderr with 64 KiB caps; enforce timeout; kill on timeout.
- Non-zero exit / timeout = `HookExecutionError`.

HTTP runner:

- `httpx.AsyncClient(timeout=..., follow_redirects=False)`.
- Validate URL/headers (reuse D12a helpers); POST JSON payload.
- Read body with cap; non-2xx = `HookExecutionError`.

Response parsing:

```python
def _parse_response(text: str) -> HookResult:
    stripped = text.strip()
    if not stripped:
        return HookResult()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return HookResult(context=stripped[:MAX_CONTEXT_CHARS])
    if not isinstance(data, dict):
        return HookResult(context=stripped[:MAX_CONTEXT_CHARS])
    decision = data.get("decision")
    if decision not in (None, "allow", "deny"):
        raise HookExecutionError("invalid decision")
    args = data.get("args")
    if args is not None and not isinstance(args, dict):
        raise HookExecutionError("args must be an object")
    context = data.get("context")
    if context is not None and not isinstance(context, str):
        raise HookExecutionError("context must be a string")
    return HookResult(
        decision=decision,
        reason=str(data.get("reason") or ""),
        args=args,
        result=data.get("result"),
        context=(context or "")[:MAX_CONTEXT_CHARS],
    )
```

- [ ] **Step 4: Run executor tests**

Run: `uv run pytest packages/agentbox-api/tests/test_plugin_hooks_executor.py -q --timeout=60`
Expected: PASS.

---

### Task 3: Capability and runtime effects

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/plugin_hooks.py`
- Test: `packages/agentbox-api/tests/test_plugin_hooks_capability.py`

**Interfaces:**
- Produces: `PluginHookRuntime`, `get_plugin_hook_runtime`.
- Produces: `PluginHooks(AbstractCapability)`.
- Produces: `PluginHookRef(plugin, root, data, hook)`.

- [ ] **Step 1: Write failing capability tests**

Use a fake run context and `ToolCallPart`/`ToolDefinition` objects, or a small
`Agent` with `TestModel`/`FunctionModel` to trigger a tool call. At minimum test
the capability methods directly:

```python
async def test_before_tool_denies(monkeypatch):
    hooks = PluginHooks(
        runtime=PluginHookRuntime(),
        session_id="s1",
        project_id="p1",
        project_root=str(tmp_path),
        refs=[ref_for(decision="deny", reason="no secrets")],
    )
    with pytest.raises(ToolFailed, match="no secrets"):
        await hooks.before_tool_execute(
            fake_ctx(),
            call=ToolCallPart(tool_name="write_file", args={}, tool_call_id="c1"),
            tool_def=fake_tool_def("write_file"),
            args={"path": "a"},
        )
```

Add tests for:

- allow + args replacement;
- context accumulated then appended in after_tool;
- result replacement + context;
- tool_error result recovery and context-as-ToolFailed;
- run_start context enqueued as request-scoped system prompt;
- session_start once per runtime;
- session_end on `end_session`;
- matcher filtering;
- ordering across two hooks;
- `on_error=ignore` vs `deny`.

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-api/tests/test_plugin_hooks_capability.py -q --timeout=60`
Expected: FAIL.

- [ ] **Step 3: Implement runtime**

```python
@dataclass(frozen=True)
class PluginHookRef:
    plugin: str
    root: pathlib.Path
    data: pathlib.Path
    hook: PluginHook


class PluginHookRuntime:
    def __init__(self):
        self.started: set[str] = set()
        self.active: dict[str, tuple[PluginHookRef, ...]] = {}
        self.executor = HookExecutor()

    async def ensure_started(self, session_id, refs, context):
        if session_id in self.started:
            return ()
        self.started.add(session_id)
        self.active[session_id] = tuple(refs)
        return await self._run_context_hooks("session_start", refs, context)

    async def end_session(self, session_id):
        refs = self.active.pop(session_id, ())
        self.started.discard(session_id)
        if refs:
            await self._run_side_effect_hooks("session_end", refs, ...)

    async def end_all(self):
        for session_id in list(self.active):
            await self.end_session(session_id)
```

- [ ] **Step 4: Implement `PluginHooks`**

Class fields: runtime, session_id, project_id, project_root, refs, executor,
`_tool_context: dict[str, list[str]]`.

Methods:

- `before_run(ctx)`:
  - build base context;
  - `session_context = await runtime.ensure_started(...)`;
  - `run_context = await self._run_context_hooks("run_start", ...)`;
  - combined = session_context + run_context;
  - if combined: `ctx.enqueue(SystemPromptPart(content="\n\n".join(combined), scope="request"))`.
- `after_run(ctx, *, result)`: run `run_end` hooks; return result.
- `on_run_error(ctx, *, error)`: run `run_error` hooks; `raise error`.
- `before_tool_execute(ctx, *, call, tool_def, args)`:
  - filter refs by event and matcher;
  - for each hook: execute; on error apply `on_error`; on deny raise
    `ToolFailed(result.reason or "denied by plugin hook")`;
  - if result.args is not None: `args = result.args`;
  - accumulate `result.context` in `_tool_context[call.tool_call_id]`.
- `after_tool_execute(ctx, *, call, tool_def, args, result)`:
  - take/pop context; run after hooks; if `hook_result.result is not None`,
    `result = hook_result.result`; append context strings to result with a helper
    that handles `str` and `ToolReturn`.
- `on_tool_execute_error(ctx, *, call, tool_def, args, error)`:
  - run tool_error hooks; first/last `result` wins; if none and context exists,
    `raise ToolFailed(f"{context}\n\n{error}")`; else `raise error`.
- Helpers `_execute_refs`, `_run_context_hooks`, `_run_side_effect_hooks`,
  `_append_context`, `_jsonable`.
- `_jsonable` serializes str/dict/list/pydantic/`ToolReturn`/binary descriptors
  and truncates.

- [ ] **Step 5: Run capability tests**

Run: `uv run pytest packages/agentbox-api/tests/test_plugin_hooks_capability.py -q --timeout=60`
Expected: PASS.

---

### Task 4: Agent/Harness/API lifecycle wiring

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/agent_factory.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/harness.py`
- Modify: `packages/agentbox-api/src/agentbox_api/skills.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`
- Modify: `packages/agentbox-api/src/agentbox_api/acp_server.py`
- Modify: `packages/agentbox-api/src/agentbox_api/a2a_executor.py`
- Modify: `packages/agentbox-api/src/agentbox_api/subagent_sessions.py`
- Modify: `packages/agentbox-api/src/agentbox_api/runtime.py`
- Modify: `packages/agentbox-api/src/agentbox_api/app.py`
- Test: `packages/agentbox-api/tests/test_plugin_hooks_wiring.py`

**Interfaces:**
- `build_agent(..., plugin_hooks=None)` adds the capability.
- `Harness(..., plugin_hooks=None)` forwards it.
- `PreparedAgent.plugin_hooks`.
- `get_plugin_hook_runtime()`; `end_session`/`end_all`.

- [ ] **Step 1: Write failing wiring tests**

```python
async def test_prepare_agent_attaches_plugin_hooks(tmp_path, plugin_with_hook):
    prepared = await prepare_agent(... project_id="prj", ...)
    assert prepared.plugin_hooks is not None


async def test_harness_receives_plugin_hooks(...):
    ...
```

Also test `delete_session_data` calls `end_session` and app shutdown calls
`end_all` using monkeypatched runtime methods.

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-api/tests/test_plugin_hooks_wiring.py -q --timeout=60`
Expected: FAIL.

- [ ] **Step 3: Implement wiring**

`agent_factory.py`:

```python
def build_agent(..., plugin_hooks=None) -> Agent:
    capabilities = []
    if context_editing ...:
        capabilities.append(ProcessHistory(...))
    if plugin_hooks is not None:
        capabilities.append(plugin_hooks)
    return Agent(..., capabilities=capabilities or None)
```

`harness.py` stores `self.plugin_hooks` and passes it to `build_agent`.

`skills.py`:

- Import `PluginHooks`, `PluginHookRef`, `get_plugin_hook_runtime`.
- After `plugin_service` is built, collect enabled plugin hooks:

```python
hook_refs = [
    PluginHookRef(
        plugin=plugin.manifest.name,
        root=plugin.root,
        data=plugin_service.data_dir / plugin.manifest.name,
        hook=hook,
    )
    for plugin in await plugin_service.enabled_plugins(project_id, project_root)
    if plugin.manifest is not None
    for hook in plugin.hooks
]
plugin_hooks = (
    PluginHooks(
        get_plugin_hook_runtime(),
        session_id,
        project_id,
        project_root,
        tuple(hook_refs),
    )
    if session_id and hook_refs
    else None
)
```

- Add `plugin_hooks` to `PreparedAgent`.

All Harness construction sites pass `plugin_hooks=prepared.plugin_hooks` (web,
ACP, A2A, subagent).

`runtime.py` `delete_session_data`: call
`await get_plugin_hook_runtime().end_session(session_id)` before/after deletion
(idempotent).

`app.py` shutdown: `await get_plugin_hook_runtime().end_all()` before other
shutdown.

- [ ] **Step 4: Run wiring tests**

Run: `uv run pytest packages/agentbox-api/tests/test_plugin_hooks_wiring.py -q --timeout=60`
Expected: PASS.

---

### Task 5: Plugin UI hook summaries and trust warning

**Files:**
- Modify: `apps/web/src/api/endpoints.ts`
- Modify: `apps/web/src/pages/PluginsPage.tsx`
- Test: `apps/web/src/pages/PluginsPage.test.tsx`

**Interfaces:**
- `PluginHookInfo = {id, event, tools, action, command, url, timeout_ms, on_error}`.
- `PluginInfo.hooks`.
- Plugin table hook count; details list hooks; enable confirmation copy.

- [ ] **Step 1: Write failing UI test**

```tsx
test("shows plugin hooks and warns about command execution", async () => {
  mockPluginWithHook();
  renderPage();
  expect(await screen.findByText("1 hook")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Details" }));
  expect(await screen.findByText("after_tool")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Enable" }));
  expect(
    await screen.findByText(/can run commands and call HTTP/i),
  ).toBeInTheDocument();
});
```

- [ ] **Step 2: Run and verify failure**

Run: `cd apps/web && bun run test -- PluginsPage`
Expected: FAIL.

- [ ] **Step 3: Implement**

- Add `PluginHookInfo` and `hooks` to `PluginInfo`.
- Table `Components`/new `Hooks` column shows `hooks.length`.
- Details drawer section lists id, event, matcher, action, command/URL, timeout,
  on_error.
- Enable confirmation text explicitly mentions commands, HTTP, arg mutation,
  denial, and result replacement.
- Update test mocks to include `hooks: []` where needed.

- [ ] **Step 4: Run UI test**

Run: `cd apps/web && bun run test -- PluginsPage`
Expected: PASS.

---

### Task 6: End-to-end hook test and full verification

- [ ] **Step 1: Add a fake command hook fixture**

Create a temp plugin script that reads JSON from stdin and returns a JSON
decision/args/context/result. Use `command: "python"` with
`args: ["${PLUGIN_ROOT}/hook.py"]`.

- [ ] **Step 2: Add an integration test**

Enable the plugin, build an agent/session, trigger a native tool call via a
`FunctionModel`/`TestModel`, and assert:

- `before_tool` deny prevents execution and surfaces `ToolFailed`;
- argument mutation reaches the tool;
- `after_tool` result replacement/context is model-visible;
- `session_start` context is enqueued once;
- `session_end` runs on deletion;
- disabling the plugin removes hooks on the next run.

- [ ] **Step 3: Regenerate API artifacts if plugin serialization changed**

```powershell
uv run python apps/web/scripts/gen-openapi.py
cd apps/web
bun run codegen
```

- [ ] **Step 4: Run checks and tests**

```powershell
uv run ruff check --fix packages
uv run ty check packages
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-api -q
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-providers -q
cd apps/web
bun run test
bun run build
```

Expected: clean checks; tests pass or skip.

- [ ] **Step 5: Update ROADMAP**

Mark D12b complete with the spec/plan paths; leave no D12 deferred rows.
