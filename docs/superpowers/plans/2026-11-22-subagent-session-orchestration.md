# Subagent Session Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the in-process delegation/allow-list implementation with unrestricted, session-based subagent orchestration: any session can discover agent configurations, start subagent sessions using any agent, monitor live output, wait for completion, and cancel recursively.

**Architecture:** The harness exposes only subagent-session tools backed by a runner protocol. The API replaces the old runner with a `SubagentSessionManager` modeled on terminal `JobManager`, keeping live jobs in memory, subscribing to the child `EventBus` for live output, persisting results in `SessionRow`, and providing wait/any/all and recursive cancellation. The old `delegate_*` path, `sub_agent_ids`, and `sub_session_*` names are deleted by a single database migration and a single code rewrite.

**Tech Stack:** Python 3.11, `uv`, pydantic-ai, FastAPI, SQLModel, Alembic, SQLite, pytest/pytest-asyncio, Ruff, Ty, React 19 + Bun/Vitest.

## Global Constraints

- Canonical vocabulary: **agent** = configuration; **session** = live instance; **subagent** = the configuration used for a child session; **subagent session** = the child session. Never use `sub_session`, `delegate_*`, or "spawn an agent" in new code or docs.
- Canonical tools: `list_agents`, `start_subagent_session`, `list_subagent_sessions`, `get_subagent_session`, `cancel_subagent_session`, `wait_subagent_session`, `wait_subagent_sessions`.
- Any agent in the database may be used as a subagent. No allow-list.
- Depth cap `3`; at most `5` running direct children per parent.
- The whole tool bundle is available only in modes that allow `write`.
- Replace, do not layer: delete old modules, symbols, tool names, and tests. No aliases, re-exports, shims, or dual paths.
- The migration drops `agent.sub_agent_ids` and renames `sessionrow.sub_session_*` to `sessionrow.subagent_session_*`.
- Python line length 100; run one package test directory per pytest invocation.
- Run Python commands from the repo root; run frontend commands from `apps/web` with Bun.
- Before every commit, run `git status` and stage only the files listed in the current task. Do not use `git add -A` and do not stage unrelated pre-existing working-tree changes.

---

## File Structure

- `packages/agentbox-harness/src/agentbox_harness/subagent_sessions.py` — new runner protocol, tool factories, tool descriptions.
- `packages/agentbox-harness/src/agentbox_harness/agent_factory.py` — build tools from the runner; no in-process delegation.
- `packages/agentbox-harness/src/agentbox_harness/harness.py` — hold `subagent_session_runner`.
- `packages/agentbox-api/src/agentbox_api/subagent_sessions.py` — new context, job, manager, runner, lifecycle helpers.
- `packages/agentbox-api/src/agentbox_api/skills.py` — prepare the new runner and depth.
- `packages/agentbox-api/src/agentbox_api/routers/sessions.py` — pass the new runner to `Harness`.
- `packages/agentbox-api/src/agentbox_api/acp_server.py` — pass the runner; recursive close.
- `packages/agentbox-api/src/agentbox_api/a2a_executor.py` — pass the runner.
- `packages/agentbox-api/src/agentbox_api/runtime.py` — import recursive cancel helper.
- `packages/agentbox-api/src/agentbox_api/app.py` — reconcile/shutdown the new manager.
- `packages/agentbox-models/src/agentbox_models/tables/core.py` — drop `Agent.sub_agent_ids`; rename session columns.
- `packages/agentbox-models/src/agentbox_models/repos/agents.py` — stop reading/writing `sub_agent_ids`.
- `apps/web/src/pages/agents/AgentFormDrawer.tsx`, `AgentsPage.tsx`, `OnboardingWizard.tsx` — remove dead allow-list form state.
- `packages/agentbox-models/alembic/versions/f7a8b9c0d1e2_subagent_session_columns.py` — drop and rename columns.

---

### Task 1: Replace harness delegation with subagent-session tools

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/subagent_sessions.py`
- Delete: `packages/agentbox-harness/src/agentbox_harness/subagents.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/agent_factory.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/harness.py`
- Modify: `packages/agentbox-api/src/agentbox_api/skills.py:23,142-149,269-284`
- Modify: `packages/agentbox-api/src/agentbox_api/subsessions.py:90-108`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py:489-495`
- Modify: `packages/agentbox-api/src/agentbox_api/acp_server.py:288-294`
- Modify: `packages/agentbox-api/src/agentbox_api/a2a_executor.py:133-139`
- Delete: `packages/agentbox-harness/tests/test_subagents.py`
- Rename: `packages/agentbox-harness/tests/test_sub_session_tools.py` -> `test_subagent_session_tools.py`
- Modify: `packages/agentbox-api/tests/test_sub_sessions.py`
- Modify: `packages/agentbox-api/tests/test_sub_session_wiring.py`

**Interfaces:**
- Consumes: `AgentSpec`, `Mode`, `Harness`, `build_agent`.
- Produces:
  - `SubagentSessionRunner` protocol with `list_agents`, `start`, `list`, `get`, `cancel`, `wait`, `wait_many`.
  - `make_subagent_session_tools(runner, parent_session_id) -> dict[str, Callable]`.
  - `build_subagent_session_tools(mode, runner, session_id) -> list[Callable]`.
  - `Harness(subagent_session_runner=...)`.
  - `PreparedAgent.subagent_session_runner`.
  - `prepare_agent(..., subagent_session_depth: int = 0)`.
  - `ApiSubSessionRunner.start(parent_session_id, subagent, task, wait)` (temporary class name; replaced in Task 3).

- [ ] **Step 1: Write the failing harness tool tests**

Replace `test_sub_session_tools.py` with `test_subagent_session_tools.py`:

```python
from agentbox_harness.agent_factory import build_subagent_session_tools
from agentbox_harness.spec import Mode
from agentbox_harness.subagent_sessions import make_subagent_session_tools


class FakeRunner:
    def __init__(self):
        self.calls = []

    async def list_agents(self):
        self.calls.append(("list_agents",))
        return "Agents:\n- child: helper"

    async def start(self, parent_session_id, subagent, task, wait):
        self.calls.append(("start", parent_session_id, subagent, task, wait))
        return f"started {subagent}"

    async def list(self, parent_session_id):
        self.calls.append(("list", parent_session_id))
        return "children"

    async def get(self, parent_session_id, subagent_session_id, max_chars):
        self.calls.append(("get", parent_session_id, subagent_session_id, max_chars))
        return "child"

    async def cancel(self, parent_session_id, subagent_session_id):
        self.calls.append(("cancel", parent_session_id, subagent_session_id))
        return "cancelled"

    async def wait(self, parent_session_id, subagent_session_id, timeout):
        self.calls.append(("wait", parent_session_id, subagent_session_id, timeout))
        return "waited"

    async def wait_many(self, parent_session_id, ids, mode, timeout):
        self.calls.append(("wait_many", parent_session_id, ids, mode, timeout))
        return "waited any"


async def test_tools_use_subagent_session_names_and_validate_task():
    runner = FakeRunner()
    tools = make_subagent_session_tools(runner, "parent-1")

    assert await tools["list_agents"]() == "Agents:\n- child: helper"
    assert await tools["start_subagent_session"]("child", "do it") == "started child"
    assert runner.calls[-1] == ("start", "parent-1", "child", "do it", False)
    assert "must not be empty" in await tools["start_subagent_session"]("child", "  ")
    assert await tools["list_subagent_sessions"]() == "children"
    assert await tools["get_subagent_session"]("child-1") == "child"
    assert await tools["cancel_subagent_session"]("child-1") == "cancelled"
    assert await tools["wait_subagent_session"]("child-1", 5) == "waited"
    assert (
        await tools["wait_subagent_sessions"](["child-1"], "any", 5)
        == "waited any"
    )


def test_bundle_is_write_mode_only_and_needs_runner_and_session():
    runner = FakeRunner()
    agent_mode = Mode(name="agent", flags={"write": True})
    ask_mode = Mode(name="ask", flags={"write": False})

    assert build_subagent_session_tools(agent_mode, runner, "s1")
    assert build_subagent_session_tools(ask_mode, runner, "s1") == []
    assert build_subagent_session_tools(agent_mode, None, "s1") == []
    assert build_subagent_session_tools(agent_mode, runner, None) == []
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_subagent_session_tools.py -q`

Expected: FAIL because `agentbox_harness.subagent_sessions` does not exist.

- [ ] **Step 3: Create the new harness module**

Create `packages/agentbox-harness/src/agentbox_harness/subagent_sessions.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from agentbox_harness.spec import Mode


class SubagentSessionRunner(Protocol):
    async def list_agents(self) -> str: ...

    async def start(
        self, parent_session_id: str, subagent: str, task: str, wait: bool
    ) -> str: ...

    async def list(self, parent_session_id: str) -> str: ...

    async def get(
        self, parent_session_id: str, subagent_session_id: str, max_chars: int
    ) -> str: ...

    async def cancel(
        self, parent_session_id: str, subagent_session_id: str
    ) -> str: ...

    async def wait(
        self, parent_session_id: str, subagent_session_id: str, timeout: int
    ) -> str: ...

    async def wait_many(
        self,
        parent_session_id: str,
        subagent_session_ids: Sequence[str],
        mode: str,
        timeout: int,
    ) -> str: ...


def make_subagent_session_tools(
    runner: SubagentSessionRunner, parent_session_id: str
) -> dict[str, Callable]:
    async def list_agents() -> str:
        """List agent configurations available as subagents."""
        return await runner.list_agents()

    async def start_subagent_session(
        subagent: str, task: str, wait: bool = False
    ) -> str:
        """Start a subagent session using the named agent configuration.

        The agent configuration is the subagent; the child session is the
        subagent session. Returns the session id immediately unless wait=True.
        """
        text = (task or "").strip()
        if not text:
            return "Subagent session failed: task must not be empty."
        return await runner.start(parent_session_id, subagent.strip(), text, wait)

    async def list_subagent_sessions() -> str:
        """List this session's subagent sessions with status and task summary."""
        return await runner.list(parent_session_id)

    async def get_subagent_session(
        subagent_session_id: str, max_chars: int = 4000
    ) -> str:
        """Read a subagent session's status and live or final output."""
        return await runner.get(parent_session_id, subagent_session_id, max_chars)

    async def cancel_subagent_session(subagent_session_id: str) -> str:
        """Cancel a subagent session and its descendants."""
        return await runner.cancel(parent_session_id, subagent_session_id)

    async def wait_subagent_session(
        subagent_session_id: str, timeout: int = 30
    ) -> str:
        """Wait for one subagent session to finish or time out."""
        return await runner.wait(parent_session_id, subagent_session_id, timeout)

    async def wait_subagent_sessions(
        subagent_session_ids: Sequence[str],
        mode: str = "all",
        timeout: int = 60,
    ) -> str:
        """Wait for all or any listed subagent sessions to finish or time out."""
        return await runner.wait_many(
            parent_session_id, subagent_session_ids, mode, timeout
        )

    return {
        "list_agents": list_agents,
        "start_subagent_session": start_subagent_session,
        "list_subagent_sessions": list_subagent_sessions,
        "get_subagent_session": get_subagent_session,
        "cancel_subagent_session": cancel_subagent_session,
        "wait_subagent_session": wait_subagent_session,
        "wait_subagent_sessions": wait_subagent_sessions,
    }


def build_subagent_session_tools(
    mode: Mode,
    runner: SubagentSessionRunner | None,
    session_id: str | None,
) -> list[Callable]:
    if runner is None or not session_id or not mode.allows("write"):
        return []
    return list(make_subagent_session_tools(runner, session_id).values())
```

Delete `packages/agentbox-harness/src/agentbox_harness/subagents.py`.

- [ ] **Step 4: Update `agent_factory.py` and `harness.py`**

In `agent_factory.py`, remove the `build_subagent_tools` import and the entire `build_subagent_tools` function, replace the import with `from agentbox_harness.subagent_sessions import build_subagent_session_tools`, and change `build_agent` to:

```python
def build_agent(
    spec: AgentSpec,
    mode: Mode,
    registry: ToolRegistry,
    model: Model,
    subagent_session_runner=None,
    session_id: str | None = None,
    stdio_toolsets: list[MCPToolset] | None = None,
) -> Agent:
    native_names: set[str] = set()
    mcp_bindings: list[McpToolBinding] = []
    for binding in spec.tool_bindings:
        if isinstance(binding, NativeToolBinding):
            native_names.add(binding.name)
        elif isinstance(binding, McpToolBinding):
            mcp_bindings.append(binding)

    tools = registry.select_tools(mode, names=native_names)
    tools.extend(
        build_subagent_session_tools(mode, subagent_session_runner, session_id)
    )
    tools = [_guard_tool(tool) for tool in tools]
    toolsets = [
        build_mcp_toolset(b)
        for b in mcp_bindings
        if not b.command or stdio_toolsets is None
    ]
    toolsets.extend(stdio_toolsets or [])
    logger.debug("agent built name={} tools={} toolsets={}", spec.name, len(tools), len(toolsets))
    return Agent(
        model=model,
        name=spec.name,
        instructions=spec.instructions,
        tools=tools,
        toolsets=toolsets,
    )
```

In `harness.py`, remove `sub_agents` from `__init__` and store/use `subagent_session_runner`:

```python
def __init__(
    self,
    registry: ToolRegistry,
    model: Model,
    store_factory,
    middleware: list[RunMiddleware] | None = None,
    compaction: CompactionConfig | None = None,
    subagent_session_runner=None,
    mcp_manager: McpSessionManager | None = None,
):
    self.registry = registry
    self.model = model
    self.store_factory = store_factory
    self.run_manager = RunManager()
    self.middleware = MiddlewarePipeline(
        middleware if middleware is not None else [CompactionMiddleware(compaction)]
    )
    self.subagent_session_runner = subagent_session_runner
    self.mcp_manager = mcp_manager or get_mcp_session_manager()
```

In `Harness.run`, call:

```python
agent = build_agent(
    spec,
    mode,
    self.registry,
    self.model,
    subagent_session_runner=self.subagent_session_runner,
    session_id=session.session_id,
    stdio_toolsets=session_tools.toolsets,
)
```

- [ ] **Step 5: Update API wiring and the temporary old runner**

In `skills.py`:

```python
from agentbox_harness.subagent_sessions import SubagentSessionRunner
```

Change the dataclass field to:

```python
class PreparedAgent:
    runtime: AgentRuntime
    spec: AgentSpec
    registry: ToolRegistry
    skills: list[Skill]
    subagent_session_runner: SubagentSessionRunner | None = None
```

Rename the `prepare_agent` parameter `sub_session_depth` to `subagent_session_depth`, and pass it to the context:

```python
subagent_session_runner = ApiSubSessionRunner(
    SubSessionContext(
        factory=factory,
        project_root=project_root,
        skills_user_dir=user_dir,
        extra_roots=[str(path) for path in resolved_extra],
        web_config=web_config,
        compaction=compaction or CompactionConfig(),
        media_max_dimension=media_max_dimension,
        media_max_bytes=media_max_bytes,
        depth=subagent_session_depth,
    )
)
return PreparedAgent(runtime, spec, registry, skills, subagent_session_runner)
```

In `subsessions.py`, change `ApiSubSessionRunner.start` to the new protocol signature and remove the allow-list check. Change the signature to `(self, parent_session_id, subagent, task, wait)`, delete the `set(parent_spec.sub_agent_ids)` check, and replace every remaining `agent_name` in that method's output strings with `subagent`:

```python
async def start(
    self,
    parent_session_id: str,
    subagent: str,
    task: str,
    wait: bool,
) -> str:
    text = (task or "").strip()
    if not text:
        return "Subagent session failed: task must not be empty."
    if self._context.depth >= MAX_SUB_SESSION_DEPTH:
        return "Subagent session failed: maximum depth reached."

    async with self._context.factory() as s:
        parent = await s.get(SessionRow, parent_session_id)
        if parent is None:
            return "Subagent session failed: parent session not found."
        running = (
            await s.execute(
                select(SessionRow).where(
                    SessionRow.parent_session_id == parent_session_id,
                    SessionRow.sub_session_status == "running",
                )
            )
        ).scalars().all()
        project_id = parent.project_id
    if len(running) >= MAX_SUB_SESSIONS:
        return (
            f"Subagent session failed: at most {MAX_SUB_SESSIONS} children "
            "can run at once."
        )

    child_id = uuid.uuid4().hex
    try:
        prepared = await prepare_agent(
            self._context.factory,
            subagent,
            self._context.project_root,
            self._context.skills_user_dir,
            session_id=child_id,
            session_mode="agent",
            media_max_dimension=self._context.media_max_dimension,
            media_max_bytes=self._context.media_max_bytes,
            web_config=self._context.web_config,
            extra_roots=self._context.extra_roots,
            compaction=self._context.compaction,
            subagent_session_depth=self._context.depth + 1,
        )
    except KeyError:
        return f"Subagent session failed: unknown agent {subagent}."
    except ValueError as exc:
        return f"Subagent session failed: {exc}"
```

Keep the rest of the old runner for now; Task 3 replaces it. Add the three missing protocol methods so the old runner is still usable between Tasks 1 and 3. Add `import contextlib` at the top of `subsessions.py`:

```python
    async def list_agents(self) -> str:
        async with self._context.factory() as s:
            rows = (
                await s.execute(select(Agent).order_by(Agent.name))
            ).scalars().all()
        if not rows:
            return "No agents."
        return "Agents:\n" + "\n".join(
            f"- {row.name}: {row.description}" for row in rows
        )

    async def wait(
        self, parent_session_id: str, subagent_session_id: str, timeout: int
    ) -> str:
        active = _active.get(subagent_session_id)
        if active is not None:
            task_handle, _run = active
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task_handle), timeout)
        return await self.get(parent_session_id, subagent_session_id, 4000)

    async def wait_many(
        self,
        parent_session_id: str,
        subagent_session_ids: Sequence[str],
        mode: str,
        timeout: int,
    ) -> str:
        tasks = []
        for sid in subagent_session_ids:
            active = _active.get(sid)
            if active is not None:
                tasks.append(
                    asyncio.create_task(
                        asyncio.wait_for(asyncio.shield(active[0]), timeout)
                    )
                )
        if tasks:
            if mode == "any":
                _, pending = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
            else:
                await asyncio.gather(*tasks, return_exceptions=True)
        return "\n\n".join(
            [
                await self.get(parent_session_id, sid, 4000)
                for sid in subagent_session_ids
            ]
        )
```

In `routers/sessions.py`, `acp_server.py`, and `a2a_executor.py`, rename the `Harness` argument:

```python
subagent_session_runner=prepared.subagent_session_runner
```

In `acp_server.py`, also rename `AcpSession.sub_session_runner` to `subagent_session_runner` and update the two constructor calls/reads.

- [ ] **Step 6: Update API tests for the new runner signature and field**

In `test_sub_sessions.py`, change calls from:

```python
await runner.start("parent-session", prepared.spec, "child", "do work", wait=False)
```

to:

```python
await runner.start("parent-session", "child", "do work", wait=False)
```

In `test_sub_session_wiring.py`, assert `prepared.subagent_session_runner is not None`.

- [ ] **Step 7: Run harness and API tests**

Run:

```powershell
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-api -q
```

Expected: PASS. If a test still imports `agentbox_harness.subagents`, update it to the new module or delete it; the old module must not exist.

- [ ] **Step 8: Commit**

```powershell
git add packages/agentbox-harness packages/agentbox-api
git commit -m "refactor(harness): replace delegation with subagent session tools"
```

---

### Task 2: Drop `sub_agent_ids`, rename session columns, update forms

**Files:**
- Create: `packages/agentbox-models/alembic/versions/f7a8b9c0d1e2_subagent_session_columns.py`
- Rename: `packages/agentbox-models/tests/test_sub_session_fields.py` -> `test_subagent_session_fields.py`
- Create: `packages/agentbox-models/tests/test_subagent_session_migration.py`
- Modify: `packages/agentbox-models/src/agentbox_models/tables/core.py:39-55,76-89`
- Modify: `packages/agentbox-models/src/agentbox_models/repos/agents.py:80-82,112-121`
- Modify: `packages/agentbox-harness/src/agentbox_harness/spec.py:43-51`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/agents.py:38-47,85-101`
- Modify: `packages/agentbox-api/src/agentbox_api/subsessions.py` column references
- Modify: `apps/web/src/pages/agents/AgentFormDrawer.tsx:39-47,88-90,152-161,177`
- Modify: `apps/web/src/pages/AgentsPage.tsx:98`
- Modify: `apps/web/src/onboarding/OnboardingWizard.tsx:148`
- Modify: `apps/web/src/pages/agents/AgentFormDrawer.test.tsx:36,46`
- Modify: `apps/web/src/pages/AgentsPage.test.tsx:25`
- Modify: `packages/agentbox-api/tests/test_acp.py:99`, `test_acp_stdio.py:39`, `test_chat.py:28`, `test_mcp_apps.py:46`, `test_send.py:40`, `test_stdio_mcp.py:53`
- Modify: `packages/agentbox-api/tests/test_sub_sessions.py:28`, `test_sub_session_wiring.py:20`
- Modify: `packages/agentbox-models/tests/test_core_tables.py:30`
- Modify: `packages/agentbox-harness/tests/test_spec.py:24`

**Interfaces:**
- Consumes: `AgentSpec`, `AgentRepository`, `AgentCreate`.
- Produces: schema without `agent.sub_agent_ids`; `SessionRow.subagent_session_status/error/output/depth`; form payload without `sub_agent_ids`.

- [ ] **Step 1: Write the failing migration test**

Create `packages/agentbox-models/tests/test_subagent_session_migration.py`:

```python
import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def _config(db) -> Config:
    config = Config("packages/agentbox-models/alembic.ini")
    config.set_main_option("script_location", "packages/agentbox-models/alembic")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db.as_posix()}")
    return config


def test_migration_drops_and_renames(tmp_path):
    db = tmp_path / "mig.db"
    config = _config(db)
    command.upgrade(config, "e5f6a7b8c9d0")

    engine = sa.create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO agent "
                "(id, name, description, instructions, model_id, tool_bindings, "
                "mode_definitions, sub_agent_ids, created_at) "
                "VALUES ('a1', 'a', 'd', 'i', 'm1', '[]', '[]', '[\"x\"]', "
                "'2026-01-01 00:00:00')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO sessionrow "
                "(id, project_id, agent_id, sub_session_status, sub_session_depth, "
                "created_at) VALUES ('s1', 'p', 'a1', 'running', 1, "
                "'2026-01-01 00:00:00')"
            )
        )

    command.upgrade(config, "head")

    inspector = sa.inspect(engine)
    agent_columns = {column["name"] for column in inspector.get_columns("agent")}
    session_columns = {
        column["name"] for column in inspector.get_columns("sessionrow")
    }
    assert "sub_agent_ids" not in agent_columns
    assert "subagent_session_status" in session_columns
    assert "sub_session_status" not in session_columns
    with engine.connect() as conn:
        value = conn.execute(
            sa.text(
                "SELECT subagent_session_status FROM sessionrow WHERE id = 's1'"
            )
        ).scalar_one()
    assert value == "running"

    command.downgrade(config, "e5f6a7b8c9d0")
    inspector = sa.inspect(engine)
    assert "sub_agent_ids" in {c["name"] for c in inspector.get_columns("agent")}
    assert "sub_session_status" in {
        c["name"] for c in inspector.get_columns("sessionrow")
    }
    engine.dispose()
```

- [ ] **Step 2: Run the migration test and verify it fails**

Run: `uv run pytest packages/agentbox-models/tests/test_subagent_session_migration.py -q`

Expected: FAIL because revision `f7a8b9c0d1e2` does not exist.

- [ ] **Step 3: Write the migration**

Create `packages/agentbox-models/alembic/versions/f7a8b9c0d1e2_subagent_session_columns.py`:

```python
"""subagent session columns

Revision ID: f7a8b9c0d1e2
Revises: e5f6a7b8c9d0
Create Date: 2026-11-22 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sessionrow") as batch:
        batch.alter_column(
            "sub_session_status",
            new_column_name="subagent_session_status",
            existing_type=sa.String(),
        )
        batch.alter_column(
            "sub_session_error",
            new_column_name="subagent_session_error",
            existing_type=sa.String(),
        )
        batch.alter_column(
            "sub_session_output",
            new_column_name="subagent_session_output",
            existing_type=sa.String(),
        )
        batch.alter_column(
            "sub_session_depth",
            new_column_name="subagent_session_depth",
            existing_type=sa.Integer(),
        )
    with op.batch_alter_table("agent") as batch:
        batch.drop_column("sub_agent_ids")


def downgrade() -> None:
    with op.batch_alter_table("agent") as batch:
        batch.add_column(
            sa.Column(
                "sub_agent_ids",
                sa.String(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
    with op.batch_alter_table("sessionrow") as batch:
        batch.alter_column(
            "subagent_session_status",
            new_column_name="sub_session_status",
            existing_type=sa.String(),
        )
        batch.alter_column(
            "subagent_session_error",
            new_column_name="sub_session_error",
            existing_type=sa.String(),
        )
        batch.alter_column(
            "subagent_session_output",
            new_column_name="sub_session_output",
            existing_type=sa.String(),
        )
        batch.alter_column(
            "subagent_session_depth",
            new_column_name="sub_session_depth",
            existing_type=sa.Integer(),
        )
```

- [ ] **Step 4: Update the model, spec, repository, and API**

In `core.py`, remove `sub_agent_ids` from `Agent`. In `SessionRow`, rename:

```python
subagent_session_status: str | None = None
subagent_session_error: str | None = None
subagent_session_output: str | None = None
subagent_session_depth: int = 0
```

In `spec.py`, remove `sub_agent_ids: list[str] = []` from `AgentSpec`.

In `repos/agents.py`, delete `row.sub_agent_ids = json.dumps(spec.sub_agent_ids)` and remove `sub_agent_ids=json.loads(row.sub_agent_ids or "[]")` from `AgentSpec(...)`.

In `routers/agents.py`, remove `sub_agent_ids: list[str] = []` from `AgentCreate` and remove `sub_agent_ids=body.sub_agent_ids` from `_to_spec`.

In `subsessions.py`, replace every `sub_session_status`, `sub_session_error`, `sub_session_output`, `sub_session_depth` with the new names.

- [ ] **Step 5: Remove the dead form state and generated-type usage**

In `AgentFormDrawer.tsx`:
- remove `subAgentOptions` from props and its type;
- delete `const [subAgents, setSubAgents] = ...`;
- delete `sub_agent_ids: subAgents` from the body;
- delete `setSubAgents([])`.

In `AgentsPage.tsx`, delete `subAgentOptions={agentList.map((item) => item.name)}`.

In `OnboardingWizard.tsx`, delete `sub_agent_ids: []`.

In `AgentFormDrawer.test.tsx`, delete `sub_agent_ids: []` from the fixture and `subAgentOptions={[]}` from the render.

In `AgentsPage.test.tsx`, delete `sub_agent_ids: []` from the fixture.

- [ ] **Step 6: Update test seeds and field names**

Remove `sub_agent_ids=...` from the API tests listed in Files. In `test_subagent_session_fields.py`, rename the test function to `test_subagent_session_fields_roundtrip` and use the new column names:

```python
subagent_session_status="running",
subagent_session_error=None,
subagent_session_depth=1,
```

Update assertions to `child.subagent_session_status` and `child.subagent_session_depth`.

In `test_core_tables.py`, delete `sub_agent_ids="[]"`.

In `test_spec.py`, remove `sub_agent_ids=["sub"]` from the spec fixture.

- [ ] **Step 7: Run model and API tests**

Run:

```powershell
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-api -q
```

Expected: PASS, including the migration test.

- [ ] **Step 8: Regenerate API artifacts**

Run:

```powershell
uv run python apps/web/scripts/gen-openapi.py
cd apps/web
bun run codegen
```

- [ ] **Step 9: Run frontend tests and build**

Run:

```powershell
cd apps/web
bun run test
bun run build
```

Expected: PASS. If the generated schema still contains `sub_agent_ids`, rerun codegen; do not hand-edit.

- [ ] **Step 10: Commit**

```powershell
git add packages/agentbox-models packages/agentbox-harness/src/agentbox_harness/spec.py packages/agentbox-harness/tests/test_spec.py packages/agentbox-api/src/agentbox_api/routers/agents.py packages/agentbox-api/src/agentbox_api/subsessions.py packages/agentbox-api/tests apps/web/src apps/web/openapi.json apps/web/src/api/schema.d.ts
git commit -m "refactor(models): drop sub_agent_ids and rename subagent session columns"
```

---

### Task 3: Replace the API runner with `SubagentSessionManager`

**Files:**
- Create: `packages/agentbox-api/src/agentbox_api/subagent_sessions.py`
- Delete: `packages/agentbox-api/src/agentbox_api/subsessions.py`
- Modify: `packages/agentbox-api/src/agentbox_api/skills.py:23,142-149,169-183,269-284`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py:489-495`
- Modify: `packages/agentbox-api/src/agentbox_api/acp_server.py:147,262,288-294,430-439,476`
- Modify: `packages/agentbox-api/src/agentbox_api/a2a_executor.py:133-139`
- Modify: `packages/agentbox-api/src/agentbox_api/runtime.py:146,152`
- Modify: `packages/agentbox-api/src/agentbox_api/app.py:41-43,58,70`
- Modify: `packages/agentbox-api/tests/test_acp_stdio.py:83-92`
- Rename: `packages/agentbox-api/tests/test_sub_sessions.py` -> `test_subagent_sessions.py`
- Rename: `packages/agentbox-api/tests/test_sub_session_wiring.py` -> `test_subagent_session_wiring.py`
- Rename: `packages/agentbox-api/tests/test_sub_session_lifecycle.py` -> `test_subagent_session_lifecycle.py`
- Rename: `packages/agentbox-api/tests/test_sub_sessions_list.py` -> `test_subagent_sessions_list.py`

**Interfaces:**
- Consumes: `SubagentSessionRunner` from Task 1; renamed schema from Task 2.
- Produces:
  - `SubagentSessionContext`, `SubagentSessionJob`, `SubagentSessionManager`, `ApiSubagentSessionRunner`.
  - `get_subagent_session_manager()`, `reset_subagent_session_manager()`.
  - `cancel_subagent_sessions(factory, parent_session_id)`, `shutdown_subagent_sessions()`, `reconcile_running_subagent_sessions(factory)`.
  - `PreparedAgent.subagent_session_runner` returns `ApiSubagentSessionRunner`.

- [ ] **Step 1: Rename the API tests and write the new basic test file**

Rename the files listed above. In `test_subagent_sessions.py`, update imports to:

```python
from agentbox_api.subagent_sessions import (
    ApiSubagentSessionRunner,
    SubagentSessionContext,
    reset_subagent_session_manager,
)
```

Add an autouse reset in `packages/agentbox-api/tests/conftest.py`:

```python
from agentbox_api.subagent_sessions import (
    get_subagent_session_manager,
    reset_subagent_session_manager,
)


@pytest_asyncio.fixture(autouse=True)
async def _reset_subagent_session_manager():
    reset_subagent_session_manager()
    yield
    await get_subagent_session_manager().shutdown()
    reset_subagent_session_manager()
```

Update `_context` to `SubagentSessionContext` and `_prepared` to use the new field. The setup no longer sets `sub_agent_ids`; seed two agents (`parent`, `child`) and one parent session.

Add these basic tests:

```python
async def test_list_agents_includes_all_agents(tmp_path):
    engine, factory = await _setup(tmp_path)
    try:
        runner = ApiSubagentSessionRunner(_context(factory, tmp_path))
        listed = await runner.list_agents()
        assert "- child:" in listed
        assert "- parent:" in listed
    finally:
        await engine.dispose()


async def test_start_any_agent_without_allow_list(tmp_path):
    engine, factory = await _setup(tmp_path)
    try:
        runner = ApiSubagentSessionRunner(_context(factory, tmp_path))
        result = await runner.start("parent-session", "child", "do work", wait=True)
        assert "completed" in result
        assert "Hello from the test provider" in result
    finally:
        await engine.dispose()


async def test_unknown_agent_and_empty_task_and_depth(tmp_path):
    engine, factory = await _setup(tmp_path)
    try:
        deep = ApiSubagentSessionRunner(_context(factory, tmp_path, depth=3))
        assert "maximum depth" in await deep.start(
            "parent-session", "child", "x", False
        )
        runner = ApiSubagentSessionRunner(_context(factory, tmp_path))
        assert "unknown agent" in await runner.start(
            "parent-session", "missing", "x", False
        )
        assert "must not be empty" in await runner.start(
            "parent-session", "child", "  ", False
        )
    finally:
        await engine.dispose()


async def test_get_and_cancel_require_parent_ownership(tmp_path):
    engine, factory = await _setup(tmp_path)
    try:
        runner = ApiSubagentSessionRunner(_context(factory, tmp_path))
        assert (
            await runner.get("other-parent", "missing", 100)
            == "Subagent session not found."
        )
        assert (
            await runner.cancel("other-parent", "missing")
            == "Subagent session not found."
        )
    finally:
        await engine.dispose()
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `uv run pytest packages/agentbox-api/tests/test_subagent_sessions.py -q`

Expected: FAIL because `agentbox_api.subagent_sessions` does not exist.

- [ ] **Step 3: Create the new API module**

Create `packages/agentbox-api/src/agentbox_api/subagent_sessions.py` with the complete implementation below. This includes live output, wait/any/all, recursive cancel, and lifecycle helpers.

```python
from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
)
from sqlmodel import select

from agentbox_api.skills import prepare_agent
from agentbox_harness.compaction import CompactionConfig
from agentbox_harness.events import EventBus
from agentbox_harness.harness import Harness
from agentbox_harness.run import Run
from agentbox_harness.session import Session, Turn
from agentbox_harness.tools.web import WebToolConfig
from agentbox_harness.usage import context_tokens_from_usage
from agentbox_models.repos.message_log import SQLiteMessageLogStore
from agentbox_models.tables.core import Agent, SessionRow, TurnRow

MAX_SUBAGENT_SESSIONS = 5
MAX_SUBAGENT_SESSION_DEPTH = 3
OUTPUT_LIMIT = 200_000


@dataclass(frozen=True)
class SubagentSessionContext:
    factory: Any
    project_root: str
    skills_user_dir: str
    extra_roots: list[str]
    web_config: WebToolConfig | None
    compaction: CompactionConfig
    media_max_dimension: int
    media_max_bytes: int
    depth: int


@dataclass
class SubagentSessionJob:
    session_id: str
    parent_session_id: str
    subagent: str
    task: str
    depth: int
    status: str = "running"
    started_at: float = field(default_factory=time.monotonic)
    ended_at: float | None = None
    output: list[str] = field(default_factory=list)
    truncated: bool = False
    run: Run | None = None
    task_handle: asyncio.Task | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)
    result: str | None = None
    error: str | None = None

    def add_output(self, text: str) -> None:
        if not text:
            return
        self.output.append(text)
        total = sum(len(part) for part in self.output)
        while total > OUTPUT_LIMIT and self.output:
            overflow = total - OUTPUT_LIMIT
            first = self.output[0]
            if len(first) <= overflow:
                self.output.pop(0)
                total -= len(first)
            else:
                self.output[0] = first[overflow:]
                total -= overflow
        self.truncated = total >= OUTPUT_LIMIT

    def output_text(self) -> str:
        return "".join(self.output)


def _age_seconds(created_at: datetime) -> float:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return (datetime.now(UTC) - created_at).total_seconds()


async def _set_status(
    factory,
    session_id: str,
    status: str,
    error: str | None = None,
    output: str | None = None,
) -> None:
    async with factory() as s:
        row = await s.get(SessionRow, session_id)
        if row is None:
            return
        row.subagent_session_status = status
        row.subagent_session_error = error
        if output is not None:
            row.subagent_session_output = output
        s.add(row)
        await s.commit()


async def _child_rows(factory, parent_session_id: str):
    async with factory() as s:
        return (
            (
                await s.execute(
                    select(SessionRow)
                    .where(SessionRow.parent_session_id == parent_session_id)
                    .order_by(SessionRow.created_at.desc())  # ty: ignore[missing-attribute]
                )
            )
            .scalars()
            .all()
        )


async def _descendant_ids(factory, root_id: str) -> list[str]:
    ids: list[str] = []
    frontier = [root_id]
    while frontier:
        current = frontier.pop()
        for row in await _child_rows(factory, current):
            ids.append(row.id)
            frontier.append(row.id)
    return ids


async def _first_user_text(factory, session_id: str) -> str:
    async with factory() as s:
        row = (
            await s.execute(
                select(TurnRow)
                .where(TurnRow.session_id == session_id, TurnRow.role == "user")
                .order_by(TurnRow.created_at)  # ty: ignore[invalid-argument-type]
            )
        ).scalars().first()
    return row.content if row else ""


async def _latest_assistant_text(factory, session_id: str) -> str:
    async with factory() as s:
        row = (
            await s.execute(
                select(TurnRow)
                .where(
                    TurnRow.session_id == session_id,
                    TurnRow.role == "assistant",
                )
                .order_by(TurnRow.created_at.desc())  # ty: ignore[missing-attribute]
            )
        ).scalars().first()
    return row.content if row else ""


async def _agent_name(factory, agent_id: str) -> str:
    async with factory() as s:
        row = await s.get(Agent, agent_id)
    return row.name if row else agent_id


def _event_text(event) -> str | None:
    if isinstance(event, PartStartEvent):
        part = event.part
        if isinstance(part, TextPart) and part.content:
            return part.content
        return None
    if isinstance(event, PartDeltaEvent):
        delta = event.delta
        if isinstance(delta, TextPartDelta) and delta.content_delta:
            return delta.content_delta
        return None
    if isinstance(event, FunctionToolCallEvent):
        name = getattr(event.part, "tool_name", None) or getattr(
            event.part, "tool_call_id", "tool"
        )
        return f"\n[tool] {name}: started\n"
    if isinstance(event, FunctionToolResultEvent):
        name = getattr(event.part, "tool_name", None) or getattr(
            event.part, "tool_call_id", "tool"
        )
        return f"\n[tool] {name}: completed\n"
    return None


class SubagentSessionManager:
    def __init__(self) -> None:
        self._jobs: dict[str, SubagentSessionJob] = {}

    def register(self, job: SubagentSessionJob) -> None:
        self._jobs[job.session_id] = job

    def get(self, session_id: str) -> SubagentSessionJob | None:
        return self._jobs.get(session_id)

    def children(self, parent_session_id: str) -> list[SubagentSessionJob]:
        return [
            job
            for job in self._jobs.values()
            if job.parent_session_id == parent_session_id
        ]

    async def wait(self, job: SubagentSessionJob, timeout: int) -> None:
        timeout = max(1, min(600, int(timeout)))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(job.done.wait(), timeout)

    async def wait_many(
        self, jobs: list[SubagentSessionJob], mode: str, timeout: int
    ) -> None:
        if not jobs:
            return
        timeout = max(1, min(600, int(timeout)))
        waiters = [
            asyncio.create_task(self.wait(job, timeout)) for job in jobs
        ]
        if mode == "any":
            _, pending = await asyncio.wait(
                waiters,
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        else:
            await asyncio.gather(*waiters)

    def cancel(self, session_id: str) -> None:
        job = self._jobs.get(session_id)
        if job is None:
            return
        for child in [
            item
            for item in self._jobs.values()
            if item.parent_session_id == session_id
        ]:
            self.cancel(child.session_id)
        if job.run is not None:
            job.run.cancel()
        if job.task_handle is not None:
            job.task_handle.cancel()
        if job.status == "running":
            job.status = "cancelled"
            job.ended_at = time.monotonic()
        job.done.set()

    async def shutdown(self) -> None:
        for job in list(self._jobs.values()):
            self.cancel(job.session_id)
        self._jobs.clear()


_manager: SubagentSessionManager | None = None


def get_subagent_session_manager() -> SubagentSessionManager:
    global _manager
    if _manager is None:
        _manager = SubagentSessionManager()
    return _manager


def reset_subagent_session_manager() -> None:
    global _manager
    _manager = None


class ApiSubagentSessionRunner:
    def __init__(self, context: SubagentSessionContext):
        self._context = context
        self._manager = get_subagent_session_manager()

    async def list_agents(self) -> str:
        async with self._context.factory() as s:
            rows = (
                await s.execute(select(Agent).order_by(Agent.name))
            ).scalars().all()
        if not rows:
            return "No agents."
        lines = ["Agents:"]
        for row in rows:
            lines.append(f"- {row.name}: {row.description}")
        return "\n".join(lines)

    async def start(
        self,
        parent_session_id: str,
        subagent: str,
        task: str,
        wait: bool,
    ) -> str:
        text = (task or "").strip()
        if not text:
            return "Subagent session failed: task must not be empty."
        if self._context.depth >= MAX_SUBAGENT_SESSION_DEPTH:
            return "Subagent session failed: maximum depth reached."

        async with self._context.factory() as s:
            parent = await s.get(SessionRow, parent_session_id)
            if parent is None:
                return "Subagent session failed: parent session not found."
            running = (
                await s.execute(
                    select(SessionRow).where(
                        SessionRow.parent_session_id == parent_session_id,
                        SessionRow.subagent_session_status == "running",
                    )
                )
            ).scalars().all()
            project_id = parent.project_id
        if len(running) >= MAX_SUBAGENT_SESSIONS:
            return (
                f"Subagent session failed: at most {MAX_SUBAGENT_SESSIONS} "
                "children can run at once."
            )

        child_id = uuid.uuid4().hex
        try:
            prepared = await prepare_agent(
                self._context.factory,
                subagent,
                self._context.project_root,
                self._context.skills_user_dir,
                session_id=child_id,
                session_mode="agent",
                media_max_dimension=self._context.media_max_dimension,
                media_max_bytes=self._context.media_max_bytes,
                web_config=self._context.web_config,
                extra_roots=self._context.extra_roots,
                compaction=self._context.compaction,
                subagent_session_depth=self._context.depth + 1,
            )
        except KeyError:
            return f"Subagent session failed: unknown agent {subagent}."
        except ValueError as exc:
            return f"Subagent session failed: {exc}"

        async with self._context.factory() as s:
            s.add(
                SessionRow(
                    id=child_id,
                    project_id=project_id,
                    agent_id=prepared.runtime.agent_id,
                    parent_session_id=parent_session_id,
                    subagent_session_status="running",
                    subagent_session_depth=self._context.depth + 1,
                )
            )
            await s.commit()

        job = SubagentSessionJob(
            session_id=child_id,
            parent_session_id=parent_session_id,
            subagent=subagent,
            task=text,
            depth=self._context.depth + 1,
        )
        self._manager.register(job)
        job.task_handle = asyncio.create_task(self._execute(job, prepared, text))

        if wait:
            await job.done.wait()
        return (
            f"Started subagent session {child_id} with {subagent}."
            if not wait
            else await self._summary(parent_session_id, child_id, 4000)
        )

    async def _execute(self, job, prepared, text: str) -> None:
        def store_factory():
            return SQLiteMessageLogStore(self._context.factory, job.session_id)

        session = Session(
            session_id=job.session_id,
            project_root=self._context.project_root,
            agent_spec=prepared.spec,
            store=store_factory(),
            head_id=None,
            mode_name="agent",
            extra_roots=self._context.extra_roots,
        )
        harness = Harness(
            registry=prepared.registry,
            model=prepared.runtime.model,
            store_factory=store_factory,
            compaction=self._context.compaction,
            subagent_session_runner=prepared.subagent_session_runner,
        )
        bus = EventBus()
        subscription = bus.subscribe()
        drain_task = asyncio.create_task(self._drain(subscription, job))
        try:
            warnings = (await harness.prepare_mcp(session)).warnings
            for warning in warnings:
                logger.warning(
                    "subagent session mcp server unavailable session={} server={} error={}",
                    job.session_id,
                    warning.server_id,
                    warning.message,
                )
            run = await harness.run(session, text, bus)
            job.run = run
            outcome = await run.await_outcome()
            if outcome.status == "success":
                result = await run.await_result()
                output = str(result.output)
                context_tokens = context_tokens_from_usage(result.response.usage)
                await session.append(
                    Turn(
                        id=uuid.uuid4().hex,
                        role="assistant",
                        content=output,
                        parent_id=session.head_id,
                        context_tokens=context_tokens,
                    ),
                    parent_id=session.head_id,
                )
                job.status = "completed"
                job.result = output
                await _set_status(
                    self._context.factory, job.session_id, "completed", output=output
                )
            elif outcome.status == "cancelled":
                run.cancel()
                job.status = "cancelled"
                await _set_status(self._context.factory, job.session_id, "cancelled")
            else:
                job.status = "failed"
                job.error = outcome.message or "error"
                await _set_status(
                    self._context.factory,
                    job.session_id,
                    "failed",
                    job.error,
                )
        except asyncio.CancelledError:
            job.status = "cancelled"
            await _set_status(self._context.factory, job.session_id, "cancelled")
            raise
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            logger.warning(
                "subagent session failed session={} error={}", job.session_id, exc
            )
            await _set_status(
                self._context.factory,
                job.session_id,
                "failed",
                job.error,
            )
        finally:
            bus.close()
            with contextlib.suppress(asyncio.CancelledError):
                await drain_task
            job.ended_at = time.monotonic()
            job.done.set()

    async def _drain(self, subscription, job) -> None:
        async for item in subscription.stream():
            text = _event_text(item.event)
            if text:
                job.add_output(text)

    async def list(self, parent_session_id: str) -> str:
        rows = await _child_rows(self._context.factory, parent_session_id)
        if not rows:
            return "No subagent sessions."
        lines = ["Subagent sessions:"]
        for row in rows:
            job = self._manager.get(row.id)
            status = job.status if job else (row.subagent_session_status or "unknown")
            depth = job.depth if job else row.subagent_session_depth
            name = (
                job.subagent
                if job
                else await _agent_name(self._context.factory, row.agent_id)
            )
            task = (
                job.task
                if job
                else await _first_user_text(self._context.factory, row.id)
            )
            if job:
                age = (job.ended_at or time.monotonic()) - job.started_at
            else:
                age = _age_seconds(row.created_at)
            duration = (
                f" duration={(job.ended_at - job.started_at):.1f}s"
                if job is not None and job.ended_at is not None
                else ""
            )
            lines.append(
                f"- {row.id} {status} subagent={name} depth={depth} "
                f"age={age:.1f}s{duration} task={task[:80]}"
            )
        return "\n".join(lines)

    async def get(
        self, parent_session_id: str, subagent_session_id: str, max_chars: int
    ) -> str:
        return await self._summary(parent_session_id, subagent_session_id, max_chars)

    async def _summary(
        self, parent_session_id: str, subagent_session_id: str, max_chars: int
    ) -> str:
        async with self._context.factory() as s:
            row = await s.get(SessionRow, subagent_session_id)
        if row is None or row.parent_session_id != parent_session_id:
            return "Subagent session not found."

        job = self._manager.get(subagent_session_id)
        status = job.status if job else (row.subagent_session_status or "unknown")
        depth = job.depth if job else row.subagent_session_depth
        name = (
            job.subagent
            if job
            else await _agent_name(self._context.factory, row.agent_id)
        )
        task = (
            job.task
            if job
            else await _first_user_text(self._context.factory, subagent_session_id)
        )
        if job and job.status == "running":
            output = job.output_text()
        else:
            output = row.subagent_session_output or await _latest_assistant_text(
                self._context.factory, subagent_session_id
            )
            if not output and job:
                output = job.result or job.error or job.output_text()
        error = job.error if job else row.subagent_session_error
        limit = max(100, min(100_000, int(max_chars)))
        lines = [
            f"Subagent session {subagent_session_id}: {status} "
            f"(subagent {name}, depth {depth})",
            f"Task: {task}",
        ]
        if error:
            lines.append(f"Error: {error}")
        lines.append("Output:")
        lines.append((output or "(no output)")[:limit])
        return "\n".join(lines)

    async def cancel(self, parent_session_id: str, subagent_session_id: str) -> str:
        async with self._context.factory() as s:
            row = await s.get(SessionRow, subagent_session_id)
        if row is None or row.parent_session_id != parent_session_id:
            return "Subagent session not found."
        if row.subagent_session_status != "running":
            return (
                f"Subagent session {subagent_session_id} is already "
                f"{row.subagent_session_status}."
            )

        ids = [
            subagent_session_id,
            *await _descendant_ids(self._context.factory, subagent_session_id),
        ]
        tasks = []
        for sid in ids:
            job = self._manager.get(sid)
            if job is not None and job.task_handle is not None:
                tasks.append(job.task_handle)
            self._manager.cancel(sid)
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=5)
            for task in pending:
                task.cancel()
        async with self._context.factory() as s:
            for sid in ids:
                target = await s.get(SessionRow, sid)
                if target is not None and target.subagent_session_status == "running":
                    target.subagent_session_status = "cancelled"
                    s.add(target)
            await s.commit()
        return f"Cancelled subagent session {subagent_session_id}."

    async def wait(
        self, parent_session_id: str, subagent_session_id: str, timeout: int
    ) -> str:
        async with self._context.factory() as s:
            row = await s.get(SessionRow, subagent_session_id)
        if row is None or row.parent_session_id != parent_session_id:
            return "Subagent session not found."
        job = self._manager.get(subagent_session_id)
        if job is not None and job.status == "running":
            await self._manager.wait(job, timeout)
        return await self._summary(parent_session_id, subagent_session_id, 4000)

    async def wait_many(
        self,
        parent_session_id: str,
        subagent_session_ids: Sequence[str],
        mode: str,
        timeout: int,
    ) -> str:
        if not subagent_session_ids:
            return "No subagent sessions."
        if mode not in {"all", "any"}:
            return "Subagent session failed: mode must be 'all' or 'any'."

        jobs = []
        missing: list[str] = []
        for sid in subagent_session_ids:
            async with self._context.factory() as s:
                row = await s.get(SessionRow, sid)
            if row is None or row.parent_session_id != parent_session_id:
                missing.append(sid)
                continue
            job = self._manager.get(sid)
            if job is not None and job.status == "running":
                jobs.append(job)
        if jobs:
            await self._manager.wait_many(jobs, mode, timeout)

        lines: list[str] = []
        for sid in subagent_session_ids:
            if sid in missing:
                lines.append(f"- {sid}: Subagent session not found.")
            else:
                lines.append(await self._summary(parent_session_id, sid, 4000))
        return "\n\n".join(lines)


async def cancel_subagent_sessions(factory, parent_session_id: str) -> None:
    manager = get_subagent_session_manager()
    ids = await _descendant_ids(factory, parent_session_id)
    for sid in ids:
        manager.cancel(sid)
    async with factory() as s:
        for sid in ids:
            row = await s.get(SessionRow, sid)
            if row is not None and row.subagent_session_status == "running":
                row.subagent_session_status = "cancelled"
                s.add(row)
        await s.commit()


async def shutdown_subagent_sessions() -> None:
    await get_subagent_session_manager().shutdown()


async def reconcile_running_subagent_sessions(factory) -> None:
    async with factory() as s:
        rows = (
            await s.execute(
                select(SessionRow).where(
                    SessionRow.subagent_session_status == "running"
                )
            )
        ).scalars().all()
        for row in rows:
            row.subagent_session_status = "failed"
            row.subagent_session_error = "interrupted by backend restart"
            s.add(row)
        await s.commit()
```

Delete `packages/agentbox-api/src/agentbox_api/subsessions.py`.

- [ ] **Step 4: Update wiring and lifecycle imports**

In `skills.py`, replace the lazy import with:

```python
from agentbox_api.subagent_sessions import (
    ApiSubagentSessionRunner,
    SubagentSessionContext,
)
```

Construct `ApiSubagentSessionRunner(SubagentSessionContext(...))` and return it as `subagent_session_runner`.

In `routers/sessions.py`, `acp_server.py`, and `a2a_executor.py`, pass:

```python
subagent_session_runner=prepared.subagent_session_runner
```

In `acp_server.py`, replace the `AcpSession` field `sub_session_runner` with `subagent_session_runner` and update both constructor calls and reads. In `close_session`, import and call:

```python
from agentbox_api.subagent_sessions import cancel_subagent_sessions

await cancel_subagent_sessions(self._factory, session_id)
```

In `runtime.py`, replace the import and call:

```python
from agentbox_api.subagent_sessions import cancel_subagent_sessions

await cancel_subagent_sessions(factory, session_id)
```

In `app.py`, update the imports and calls:

```python
from agentbox_api.subagent_sessions import (
    reconcile_running_subagent_sessions,
    shutdown_subagent_sessions,
)

await reconcile_running_subagent_sessions(session_factory)  # lifespan startup

await shutdown_subagent_sessions()  # lifespan finally
```

- [ ] **Step 5: Update the renamed lifecycle/list/wiring tests**

In `test_subagent_session_lifecycle.py`, update imports to `agentbox_api.subagent_sessions`, field names to `subagent_session_status`/`subagent_session_depth`, and function names to `cancel_subagent_sessions`/`reconcile_running_subagent_sessions`.

In `test_subagent_sessions_list.py`, update the seeded fields to the new column names. The route still filters `parent_session_id IS NULL`; no route change is needed.

In `test_subagent_session_wiring.py`, assert `prepared.subagent_session_runner is not None`.

In `test_acp_stdio.py`, change the monkeypatch target from `"agentbox_api.subsessions.cancel_sub_sessions"` to `"agentbox_api.subagent_sessions.cancel_subagent_sessions"` and rename the fake function to `fake_cancel_subagent_sessions`.

- [ ] **Step 6: Run the API tests**

Run:

```powershell
uv run pytest packages/agentbox-api/tests/test_subagent_sessions.py -q
uv run pytest packages/agentbox-api -q
```

Expected: PASS. Update any remaining import from `agentbox_api.subsessions` or `sub_session_runner`; the old module must not exist.

- [ ] **Step 7: Commit**

```powershell
git add packages/agentbox-api
git commit -m "refactor(api): replace sub-session runner with subagent session manager"
```

---

### Task 4: Verify live monitoring, wait/any/all, and recursive cancellation

**Files:**
- Modify: `packages/agentbox-api/tests/test_subagent_sessions.py`
- Modify: `packages/agentbox-api/tests/test_subagent_session_lifecycle.py`
- Modify: `packages/agentbox-api/tests/conftest.py` if not already resetting the manager

**Interfaces:**
- Consumes: `ApiSubagentSessionRunner`, `SubagentSessionManager`, `get_subagent_session_manager`, `cancel_subagent_sessions`.
- Produces: regression coverage for live output, parallel waits, and descendant cancellation.

- [ ] **Step 1: Add the slow-provider setup and live monitoring test**

Extend `test_subagent_sessions.py` with a slow setup:

```python
async def _slow_setup(tmp_path):
    db = tmp_path / "slow.db"
    engine, factory = create_engine_and_sessionmaker(
        f"sqlite+aiosqlite:///{db.as_posix()}"
    )
    await init_db(engine)
    async with factory() as s:
        s.add(Provider(id="slow-prov", name="slow", kind="test_slow"))
        s.add(Model(id="slow-model", provider_id="slow-prov", name="slow-model"))
        s.add(
            Agent(
                id="parent-agent",
                name="parent",
                description="d",
                instructions="i",
                model_id="slow-model",
            )
        )
        s.add(
            Agent(
                id="slow-child-agent",
                name="slow-child",
                description="d",
                instructions="i",
                model_id="slow-model",
            )
        )
        s.add(Project(id="p1", name="p", path=str(tmp_path), owner_id="u1"))
        s.add(
            SessionRow(
                id="parent-session",
                project_id="p1",
                agent_id="parent-agent",
            )
        )
        await s.commit()
    return engine, factory


async def test_parallel_subagent_sessions_live_output_and_wait(tmp_path):
    engine, factory = await _slow_setup(tmp_path)
    try:
        runner = ApiSubagentSessionRunner(_context(factory, tmp_path))
        first = await runner.start(
            "parent-session", "slow-child", "first task", wait=False
        )
        second = await runner.start(
            "parent-session", "slow-child", "second task", wait=False
        )
        first_id = first.split()[3]
        second_id = second.split()[3]

        await asyncio.sleep(0.9)
        first_output = await runner.get("parent-session", first_id, 4000)
        assert "running" in first_output
        assert "Partial" in first_output

        any_result = await runner.wait_many(
            "parent-session", [first_id, second_id], "any", 6
        )
        assert "completed" in any_result or "failed" in any_result

        all_result = await runner.wait_many(
            "parent-session", [first_id, second_id], "all", 10
        )
        assert "Partial answer still running" in all_result
    finally:
        await engine.dispose()
```

- [ ] **Step 2: Add recursive cancellation tests**

Add to `test_subagent_session_lifecycle.py`:

```python
async def test_cancel_recurses_through_grandchildren(tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    try:
        async with factory() as s:
            s.add(SessionRow(id="parent", project_id="p", agent_id="a"))
            s.add(
                SessionRow(
                    id="child",
                    project_id="p",
                    agent_id="b",
                    parent_session_id="parent",
                    subagent_session_status="running",
                    subagent_session_depth=1,
                )
            )
            s.add(
                SessionRow(
                    id="grandchild",
                    project_id="p",
                    agent_id="c",
                    parent_session_id="child",
                    subagent_session_status="running",
                    subagent_session_depth=2,
                )
            )
            await s.commit()

        runner = ApiSubagentSessionRunner(
            SubagentSessionContext(
                factory=factory,
                project_root=str(tmp_path),
                skills_user_dir=str(tmp_path / "skills"),
                extra_roots=[],
                web_config=None,
                compaction=CompactionConfig(),
                media_max_dimension=1568,
                media_max_bytes=1_500_000,
                depth=0,
            )
        )
        result = await runner.cancel("parent", "child")
        assert "Cancelled subagent session child." == result
        async with factory() as s:
            child = await s.get(SessionRow, "child")
            grandchild = await s.get(SessionRow, "grandchild")
        assert child.subagent_session_status == "cancelled"
        assert grandchild.subagent_session_status == "cancelled"
    finally:
        await engine.dispose()
```

Add a manager-level test in the same file:

```python
async def test_manager_cancel_recurses_live_jobs():
    from agentbox_api.subagent_sessions import (
        SubagentSessionJob,
        SubagentSessionManager,
    )

    manager = SubagentSessionManager()
    child = SubagentSessionJob("child", "parent", "sub", "task", 1)
    grandchild = SubagentSessionJob("grandchild", "child", "sub", "task", 2)
    manager.register(child)
    manager.register(grandchild)

    manager.cancel("child")
    assert child.status == "cancelled"
    assert grandchild.status == "cancelled"
    assert child.done.is_set()
    assert grandchild.done.is_set()
```

- [ ] **Step 3: Run the focused tests**

Run:

```powershell
uv run pytest packages/agentbox-api/tests/test_subagent_sessions.py -q
uv run pytest packages/agentbox-api/tests/test_subagent_session_lifecycle.py -q
```

Expected: PASS. The slow test takes about 4 seconds; the package timeout is 60 seconds.

- [ ] **Step 4: Run the full API package**

Run: `uv run pytest packages/agentbox-api -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-api/tests
git commit -m "test(api): cover live subagent session monitoring and recursive cancel"
```

---

### Task 5: Documentation, generated artifacts, residue check, full verification

**Files:**
- Modify: `docs/architecture/03-backend.md`
- Modify: `docs/architecture/04-harness-runtime.md`
- Modify: `docs/architecture/07-protocols.md`
- Modify: `docs/architecture/10-concurrency-and-lifecycle.md`
- Modify: `docs/architecture/12-glossary-and-decisions.md`
- Modify: `docs/ROADMAP.md`
- Generated: `apps/web/openapi.json`, `apps/web/src/api/schema.d.ts`

**Interfaces:**
- Consumes: completed implementation.
- Produces: maintainer docs and repository with no forbidden residue.

- [ ] **Step 1: Update architecture docs**

Apply these content changes:

- `03-backend.md`: replace `acp_server.py`/`subsessions.py` references with `subagent_sessions.py`; describe the manager.
- `04-harness-runtime.md`: remove `sub-agent ids` from `AgentSpec`; replace the two delegation models with one: subagent sessions. State: any agent configuration may be used; tools are `list_agents`, `start_subagent_session`, `list_subagent_sessions`, `get_subagent_session`, `cancel_subagent_session`, `wait_subagent_session`, `wait_subagent_sessions`; depth 3; five concurrent; write-gated.
- `07-protocols.md`: update ACP shutdown wording to "cancels descendant subagent sessions recursively"; note child sessions are hidden from `GET /sessions`.
- `10-concurrency-and-lifecycle.md`: describe `SubagentSessionManager`, live output buffer, wait/any/all, recursive cancellation, restart reconciliation.
- `12-glossary-and-decisions.md`: add **agent**, **session**, **subagent**, **subagent session**; note the old names are removed.

- [ ] **Step 2: Update ROADMAP**

In `docs/ROADMAP.md`:
- Under "Use case 4 - ACP", note that ACP uses the shared subagent-session manager and recursive close.
- Under "Use case 1 - Agent creation", change the sub-agents row to "Subagent sessions - any agent configuration, background monitoring, wait/cancel; no allow-list".
- Add a sub-project history row: `Subagent session orchestration (unrestricted, live monitoring, recursive cancel)` with spec `specs/2026-11-22-subagent-session-orchestration-design.md` and plan `plans/2026-11-22-subagent-session-orchestration.md`.

- [ ] **Step 3: Regenerate API artifacts**

Run:

```powershell
uv run python apps/web/scripts/gen-openapi.py
cd apps/web
bun run codegen
```

- [ ] **Step 4: Run the residue check**

Run from the repo root:

```powershell
rg -n "delegate_|sub_agent_ids|sub_session|start_sub_session|list_sub_sessions|get_sub_session|cancel_sub_session|ApiSubSessionRunner|SubSessionRunner|SubSessionContext" packages apps/web/src --glob "!packages/agentbox-models/alembic/versions/**" --glob "!packages/agentbox-models/tests/test_subagent_session_migration.py"
```

Expected: no output. Only historical Alembic revisions, the migration regression test, and historical specs/plans may contain the old names.

- [ ] **Step 5: Run all checks**

Run:

```powershell
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-providers -q
uv run pytest packages/agentbox-api -q
uv run ruff check --fix packages
uv run ty check packages
cd apps/web
bun run test
bun run build
```

Expected: all PASS. If `bun run build` reports a stale `sub_agent_ids` type, rerun `bun run codegen` and rebuild.

- [ ] **Step 6: Run `git diff --check`**

Run: `git diff --check`

Expected: no output.

- [ ] **Step 7: Commit**

```powershell
git add docs apps/web/openapi.json apps/web/src/api/schema.d.ts
git commit -m "docs: document subagent session orchestration and update roadmap"
```

---

## Final Review Checklist

- [ ] No `delegate_` symbols, `sub_agent_ids`, `sub_session_*` runtime names, or old tool names remain.
- [ ] `agentbox_harness/subagents.py` and `agentbox_api/subsessions.py` no longer exist.
- [ ] Any agent configuration can be started as a subagent session; no allow-list.
- [ ] The seven canonical tools are registered in write mode and absent in Ask mode.
- [ ] Live output appears while a child is running; wait all/any and timeout work.
- [ ] Cancelling a child cancels grandchildren; parent close/delete/shutdown do the same.
- [ ] The migration drops `agent.sub_agent_ids`, renames the four session columns, and round-trips.
- [ ] Generated OpenAPI artifacts and frontend types contain no `sub_agent_ids`.
- [ ] All package tests, Ruff, Ty, frontend tests, and frontend build pass.
- [ ] Architecture docs and ROADMAP describe the canonical vocabulary.
