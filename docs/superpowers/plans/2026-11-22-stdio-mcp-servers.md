# Stdio MCP Servers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let agents configure local stdio MCP servers whose processes live for the lifetime of a session, with sandboxed cwd and env handling, plus create/edit UI and MCP Apps relay support.

**Architecture:** A harness-owned `McpSessionManager` lazily starts and pins entered `MCPToolset`s per session, then hands them to `build_agent` so runs reuse the same process. The web API, ACP, A2A, sub-sessions, and relay all use that manager. Agent definitions carry stdio config in the existing JSON `tool_bindings` column.

**Tech Stack:** Python 3.11, pydantic-ai `MCPToolset`, FastMCP `StdioTransport`, FastAPI, SQLModel, React 19 + Mantine, TanStack Query, pytest/pytest-asyncio.

## Global Constraints

- Ruff line length 100, target py311.
- Backend packages: `agentbox-harness` <- `agentbox-models` <- `agentbox-providers` <- `agentbox-api`.
- Use `loguru.logger`; never log MCP `env` or `env_passthrough` values.
- Every package runs tests with `timeout = 60` (`pytest-timeout`). Do not remove it; integration tests may raise their own marker.
- No Alembic migration: `Agent.tool_bindings` is already JSON text.
- Remote URL MCP behavior must remain unchanged.
- Existing agents with URL-only MCP must keep working, including URL-derived ids.
- Stdio server processes are session-scoped, pinned on first use, and closed on delete/close/idle/shutdown.
- cwd defaults to the project root; relative paths resolve against it; absolute paths must stay inside project root or `extra_roots`.
- Env merge: `env_passthrough` host values first, explicit `env` wins.
- Frontend uses Bun, not npm/pnpm.
- Regenerate `apps/web/openapi.json` and `apps/web/src/api/schema.d.ts` after route changes; never hand-edit `schema.d.ts`.
- Commit after every task with a conventional-commit message.

---

### Task 1: Extend MCP bindings with cwd and env pass-through

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/spec.py:28-38`
- Create: `packages/agentbox-harness/src/agentbox_harness/tools/paths.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/mcp.py:1-28`
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/terminal.py:240-258`
- Test: `packages/agentbox-harness/tests/test_mcp_tools.py`
- Test: `packages/agentbox-harness/tests/test_paths.py`

**Interfaces:**
- Produces: `resolve_project_path(value: str, project_root: str, extra_roots: list[str] | None = None) -> pathlib.Path`
- Produces: `resolve_mcp_env(binding: McpToolBinding) -> dict[str, str]`
- Produces: `build_mcp_toolset(binding: McpToolBinding, *, cwd: str | None = None) -> MCPToolset`
- Produces: `McpToolBinding.cwd: str`, `McpToolBinding.env_passthrough: list[str]`

- [ ] **Step 1: Write the failing tests**

Change the import at the top of `packages/agentbox-harness/tests/test_mcp_tools.py` to:

```python
from agentbox_harness.spec import McpToolBinding
from agentbox_harness.tools.mcp import build_mcp_toolset, mcp_toolset_id, resolve_mcp_env
```

Then append:

```python
def test_stdio_binding_passes_cwd_and_merged_env(monkeypatch):
    monkeypatch.setenv("HOST_TOKEN", "host-secret")
    binding = McpToolBinding(
        id="fs",
        command="python",
        args=["-m", "srv"],
        env={"K": "V", "HOST_TOKEN": "explicit-wins"},
        env_passthrough=["HOST_TOKEN", "NOT_SET"],
    )
    ts = build_mcp_toolset(binding, cwd="/tmp/project")
    transport = ts.client.transport
    assert transport.cwd == "/tmp/project"
    assert transport.env == {"HOST_TOKEN": "explicit-wins", "K": "V"}


def test_resolve_mcp_env_skips_missing_names(monkeypatch):
    monkeypatch.setenv("PRESENT", "1")
    binding = McpToolBinding(command="x", env_passthrough=["PRESENT", "MISSING"])
    assert resolve_mcp_env(binding) == {"PRESENT": "1"}
```

Create `packages/agentbox-harness/tests/test_paths.py`:

```python
import pathlib

import pytest

from agentbox_harness.tools.paths import resolve_project_path


def test_resolve_project_path_defaults_to_root(tmp_path):
    assert resolve_project_path("", str(tmp_path)) == tmp_path.resolve()


def test_resolve_project_path_relative_to_root(tmp_path):
    (tmp_path / "sub").mkdir()
    assert resolve_project_path("sub", str(tmp_path)) == (tmp_path / "sub").resolve()


def test_resolve_project_path_allows_extra_root(tmp_path):
    root = tmp_path / "root"
    extra = tmp_path / "extra"
    root.mkdir()
    extra.mkdir()
    assert resolve_project_path(str(extra), str(root), [str(extra)]) == extra.resolve()


def test_resolve_project_path_rejects_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ValueError, match="escapes allowed roots"):
        resolve_project_path("../outside", str(root))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_mcp_tools.py packages/agentbox-harness/tests/test_paths.py -q`
Expected: FAIL with `ModuleNotFoundError: agentbox_harness.tools.paths`, then failures for `cwd`/`env_passthrough`/`resolve_mcp_env`.

- [ ] **Step 3: Implement the fields and helper**

Modify `packages/agentbox-harness/src/agentbox_harness/spec.py`:

```python
@dataclass(frozen=True)
class McpToolBinding:
    server_url: str = ""
    tool_prefix: str = ""
    id: str = ""
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    env_passthrough: list[str] = field(default_factory=list)
    cwd: str = ""
```

Create `packages/agentbox-harness/src/agentbox_harness/tools/paths.py`:

```python
import pathlib


def resolve_project_path(
    value: str,
    project_root: str,
    extra_roots: list[str] | None = None,
) -> pathlib.Path:
    root = pathlib.Path(project_root).expanduser().resolve()
    allowed = list(
        dict.fromkeys(
            [root, *[pathlib.Path(path).expanduser().resolve() for path in extra_roots or []]]
        )
    )
    if not value or not value.strip():
        return root
    candidate = pathlib.Path(value).expanduser()
    target = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if not any(target == path or path in target.parents for path in allowed):
        raise ValueError(f"cwd escapes allowed roots: {value}")
    return target
```

Modify `packages/agentbox-harness/src/agentbox_harness/tools/mcp.py`:

```python
import os
import re

from fastmcp.client.transports import StdioTransport
from loguru import logger
from pydantic_ai.mcp import MCPToolset

from agentbox_harness.spec import McpToolBinding


def mcp_toolset_id(binding: McpToolBinding) -> str:
    """Stable server id used to route MCP App relay requests."""
    return binding.id or _slug(binding.server_url) or _slug(binding.command) or "mcp"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def resolve_mcp_env(binding: McpToolBinding) -> dict[str, str]:
    merged = {
        name: os.environ[name]
        for name in binding.env_passthrough
        if name in os.environ
    }
    merged.update(binding.env)
    return merged


def build_mcp_toolset(binding: McpToolBinding, *, cwd: str | None = None) -> MCPToolset:
    logger.debug("mcp toolset built id={} stdio={}", mcp_toolset_id(binding), bool(binding.command))
    if binding.command:
        transport = StdioTransport(
            command=binding.command,
            args=binding.args,
            env=resolve_mcp_env(binding) or None,
            cwd=cwd or binding.cwd or None,
        )
        return MCPToolset(transport, id=mcp_toolset_id(binding))
    return MCPToolset(binding.server_url, id=mcp_toolset_id(binding))
```

Modify `terminal.py` so `_resolve_cwd` delegates. Replace lines 249-258 with:

```python
    def _resolve_cwd(cwd: str | None) -> pathlib.Path:
        from agentbox_harness.tools.paths import resolve_project_path

        return resolve_project_path(str(cwd or ""), project_root, [str(p) for p in allowed_roots])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/agentbox-harness/tests/test_mcp_tools.py packages/agentbox-harness/tests/test_paths.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-harness/src/agentbox_harness/spec.py packages/agentbox-harness/src/agentbox_harness/tools/paths.py packages/agentbox-harness/src/agentbox_harness/tools/mcp.py packages/agentbox-harness/src/agentbox_harness/tools/terminal.py packages/agentbox-harness/tests/test_mcp_tools.py packages/agentbox-harness/tests/test_paths.py
git commit -m "feat(harness): add cwd and env pass-through to MCP bindings"
```

---

### Task 2: Add the session-scoped stdio MCP manager

**Files:**
- Create: `packages/agentbox-harness/tests/stdio_mcp_server.py`
- Create: `packages/agentbox-harness/src/agentbox_harness/tools/mcp_session.py`
- Test: `packages/agentbox-harness/tests/test_mcp_session.py`

**Interfaces:**
- Consumes: `build_mcp_toolset`, `resolve_project_path`, `mcp_toolset_id`
- Produces: `McpWarning(server_id, message)`
- Produces: `SessionToolsets(toolsets, warnings)`
- Produces: `McpSessionManager.toolsets_for(session_id, bindings, project_root, extra_roots=None) -> SessionToolsets`
- Produces: `McpSessionManager.close_session(session_id) -> None`
- Produces: `get_mcp_session_manager() -> McpSessionManager`
- Produces: `reset_mcp_session_manager() -> None`

- [ ] **Step 1: Write the fake stdio server and failing tests**

Create `packages/agentbox-harness/tests/stdio_mcp_server.py`:

```python
"""A minimal real stdio MCP server for manager integration tests."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("agentbox-test-stdio")


@mcp.tool()
def echo(text: str) -> str:
    """Echo text back."""
    return f"echo:{text}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

Create `packages/agentbox-harness/tests/test_mcp_session.py`:

```python
import pathlib
import sys

import pytest_asyncio

from agentbox_harness.spec import McpToolBinding
from agentbox_harness.tools.mcp_session import (
    McpSessionManager,
    get_mcp_session_manager,
    reset_mcp_session_manager,
)

SERVER = pathlib.Path(__file__).with_name("stdio_mcp_server.py")


def _binding(server_id: str = "echo") -> McpToolBinding:
    return McpToolBinding(
        id=server_id,
        command=sys.executable,
        args=[str(SERVER)],
    )


@pytest_asyncio.fixture(autouse=True)
async def _manager():
    reset_mcp_session_manager()
    yield
    await get_mcp_session_manager().close_all()
    reset_mcp_session_manager()


async def test_starts_once_and_reuses(tmp_path):
    manager = McpSessionManager(start_timeout=20)
    first = await manager.toolsets_for("s1", [_binding()], str(tmp_path))
    second = await manager.toolsets_for("s1", [_binding("changed")], str(tmp_path))

    assert len(first.toolsets) == 1
    assert first.warnings == []
    assert second.toolsets[0] is first.toolsets[0]
    assert manager._entries["s1"].bindings[0].id == "echo"

    await manager.close_session("s1")


async def test_pins_empty_stdio_set(tmp_path):
    manager = McpSessionManager(start_timeout=20)
    first = await manager.toolsets_for("s1", [], str(tmp_path))
    second = await manager.toolsets_for("s1", [_binding()], str(tmp_path))

    assert first.toolsets == []
    assert second.toolsets == []
    assert "s1" in manager._entries

    await manager.close_session("s1")


async def test_concurrent_calls_start_once(tmp_path):
    import asyncio

    manager = McpSessionManager(start_timeout=20)
    results = await asyncio.gather(
        manager.toolsets_for("s1", [_binding()], str(tmp_path)),
        manager.toolsets_for("s1", [_binding()], str(tmp_path)),
    )

    assert len(results[0].toolsets) == 1
    assert results[0].toolsets[0] is results[1].toolsets[0]
    assert len(manager._entries["s1"].toolsets) == 1

    await manager.close_session("s1")


async def test_close_session_is_idempotent(tmp_path):
    manager = McpSessionManager(start_timeout=20)
    await manager.toolsets_for("s1", [_binding()], str(tmp_path))
    await manager.close_session("s1")
    await manager.close_session("s1")
    assert "s1" not in manager._entries


async def test_start_failure_warns_and_continues(tmp_path):
    manager = McpSessionManager(start_timeout=5)
    bindings = [
        McpToolBinding(id="broken", command="definitely-not-a-real-command-xyz"),
        _binding("echo"),
    ]
    result = await manager.toolsets_for("s1", bindings, str(tmp_path))

    assert len(result.toolsets) == 1
    assert [w.server_id for w in result.warnings] == ["broken"]

    await manager.close_session("s1")


async def test_env_values_are_not_logged(tmp_path):
    from loguru import logger

    messages: list[str] = []
    sink = logger.add(lambda message: messages.append(str(message)), level="DEBUG")
    try:
        manager = McpSessionManager(start_timeout=20)
        binding = McpToolBinding(
            id="echo",
            command=sys.executable,
            args=[str(SERVER)],
            env={"SUPER_SECRET": "do-not-log-me"},
        )
        await manager.toolsets_for("s1", [binding], str(tmp_path))
        await manager.close_session("s1")
    finally:
        logger.remove(sink)

    assert all("do-not-log-me" not in message for message in messages)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_mcp_session.py -q`
Expected: FAIL with `ModuleNotFoundError: agentbox_harness.tools.mcp_session`.

- [ ] **Step 3: Implement the manager**

Create `packages/agentbox-harness/src/agentbox_harness/tools/mcp_session.py`:

```python
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from loguru import logger
from pydantic_ai.mcp import MCPToolset

from agentbox_harness.spec import McpToolBinding
from agentbox_harness.tools.mcp import build_mcp_toolset, mcp_toolset_id
from agentbox_harness.tools.paths import resolve_project_path


@dataclass(frozen=True)
class McpWarning:
    server_id: str
    message: str


@dataclass
class SessionToolsets:
    toolsets: list[MCPToolset] = field(default_factory=list)
    warnings: list[McpWarning] = field(default_factory=list)


@dataclass
class _SessionEntry:
    bindings: list[McpToolBinding]
    toolsets: list[MCPToolset]
    warnings: list[McpWarning]
    last_used: float


class McpSessionManager:
    def __init__(self, start_timeout: float = 30.0) -> None:
        self.start_timeout = start_timeout
        self._entries: dict[str, _SessionEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._clock = time.monotonic

    async def toolsets_for(
        self,
        session_id: str,
        bindings: list[McpToolBinding],
        project_root: str,
        extra_roots: list[str] | None = None,
    ) -> SessionToolsets:
        stdio = [b for b in bindings if isinstance(b, McpToolBinding) and b.command]
        entry = self._entries.get(session_id)
        if entry is not None:
            entry.last_used = self._clock()
            return SessionToolsets(list(entry.toolsets))
        lock = self._locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            entry = self._entries.get(session_id)
            if entry is None:
                entry = await self._create_entry(session_id, stdio, project_root, extra_roots)
                self._entries[session_id] = entry
            entry.last_used = self._clock()
            return SessionToolsets(list(entry.toolsets), list(entry.warnings))

    async def _create_entry(
        self,
        session_id: str,
        stdio: list[McpToolBinding],
        project_root: str,
        extra_roots: list[str] | None,
    ) -> _SessionEntry:
        entry = _SessionEntry(
            bindings=stdio,
            toolsets=[],
            warnings=[],
            last_used=self._clock(),
        )
        results = await asyncio.gather(
            *(
                self._start(session_id, binding, project_root, extra_roots)
                for binding in stdio
            )
        )
        for toolset, warning in results:
            if toolset is not None:
                entry.toolsets.append(toolset)
            if warning is not None:
                entry.warnings.append(warning)
        return entry

    async def _start(
        self,
        session_id: str,
        binding: McpToolBinding,
        project_root: str,
        extra_roots: list[str] | None,
    ) -> tuple[MCPToolset | None, McpWarning | None]:
        server_id = mcp_toolset_id(binding)
        cwd = resolve_project_path(binding.cwd, project_root, extra_roots)
        try:
            toolset = build_mcp_toolset(binding, cwd=str(cwd))
            await asyncio.wait_for(toolset.__aenter__(), timeout=self.start_timeout)
            return toolset, None
        except Exception as exc:
            logger.warning(
                "mcp server failed to start server={} error={}",
                server_id,
                type(exc).__name__,
            )
            return None, McpWarning(server_id, f"{type(exc).__name__}: {exc}")

    def touch(self, session_id: str) -> None:
        entry = self._entries.get(session_id)
        if entry is not None:
            entry.last_used = self._clock()

    async def close_session(self, session_id: str) -> None:
        entry = self._entries.pop(session_id, None)
        self._locks.pop(session_id, None)
        if entry is None:
            return
        for toolset in entry.toolsets:
            try:
                await toolset.__aexit__(None, None, None)
            except Exception:
                logger.warning("mcp toolset close failed session={}", session_id)

    async def close_all(self) -> None:
        for session_id in list(self._entries):
            await self.close_session(session_id)


_manager: McpSessionManager | None = None


def get_mcp_session_manager() -> McpSessionManager:
    global _manager
    if _manager is None:
        _manager = McpSessionManager()
    return _manager


def reset_mcp_session_manager() -> None:
    global _manager
    _manager = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/agentbox-harness/tests/test_mcp_session.py -q`
Expected: PASS. The fake subprocess uses `sys.executable` and the script path; no network.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-harness/src/agentbox_harness/tools/mcp_session.py packages/agentbox-harness/tests/stdio_mcp_server.py packages/agentbox-harness/tests/test_mcp_session.py
git commit -m "feat(harness): add session-scoped stdio MCP manager"
```

---

### Task 3: Add idle sweeps and cwd escape warnings

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/mcp_session.py`
- Test: `packages/agentbox-harness/tests/test_mcp_session.py`

**Interfaces:**
- Consumes: `McpSessionManager` from Task 2
- Produces: `sweep_idle(ttl_seconds)` behavior and cwd warning behavior

- [ ] **Step 1: Write the failing tests**

Append to `packages/agentbox-harness/tests/test_mcp_session.py`:

```python
async def test_idle_sweep_closes_entry(tmp_path):
    manager = McpSessionManager(start_timeout=20)
    await manager.toolsets_for("s1", [_binding()], str(tmp_path))
    await manager.sweep_idle(0)
    assert "s1" not in manager._entries


async def test_cwd_escape_warns_and_starts_nothing(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    manager = McpSessionManager(start_timeout=20)
    binding = McpToolBinding(
        id="echo",
        command=sys.executable,
        args=[str(SERVER)],
        cwd="../outside",
    )
    result = await manager.toolsets_for("s1", [binding], str(root))

    assert result.toolsets == []
    assert result.warnings[0].server_id == "echo"
    assert "escapes allowed roots" in result.warnings[0].message

    await manager.close_session("s1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_mcp_session.py -q`
Expected: FAIL with `AttributeError: 'McpSessionManager' object has no attribute 'sweep_idle'` and an uncaught `ValueError` for the cwd escape.

- [ ] **Step 3: Implement sweep and cwd warning handling**

Add to `McpSessionManager`:

```python
    async def sweep_idle(self, ttl_seconds: float) -> None:
        now = self._clock()
        stale = [
            session_id
            for session_id, entry in list(self._entries.items())
            if now - entry.last_used >= ttl_seconds
        ]
        for session_id in stale:
            await self.close_session(session_id)
        if stale:
            logger.debug("mcp idle sweep closed count={}", len(stale))
```

Make `_start` tolerate a rejected cwd by returning a warning instead of raising. Replace the `cwd = resolve_project_path(...)` line with:

```python
        try:
            cwd = resolve_project_path(binding.cwd, project_root, extra_roots)
        except ValueError as exc:
            logger.warning("mcp cwd rejected session={} server={}", session_id, server_id)
            return None, McpWarning(server_id, str(exc))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/agentbox-harness/tests/test_mcp_session.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-harness/src/agentbox_harness/tools/mcp_session.py packages/agentbox-harness/tests/test_mcp_session.py
git commit -m "test(harness): cover MCP idle sweep, cwd sandbox, and env secrecy"
```

---

### Task 4: Wire the manager into the harness and agent factory

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/session.py:52-59`
- Modify: `packages/agentbox-harness/src/agentbox_harness/agent_factory.py:44-78`
- Modify: `packages/agentbox-harness/src/agentbox_harness/harness.py:19-128`
- Test: `packages/agentbox-harness/tests/test_agent_factory.py`
- Test: `packages/agentbox-harness/tests/test_harness_mcp.py`

**Interfaces:**
- Consumes: `McpSessionManager`, `SessionToolsets`
- Produces: `Session.extra_roots: list[str]`
- Produces: `build_agent(..., stdio_toolsets: list[MCPToolset] | None = None)`
- Produces: `Harness(..., mcp_manager=None)` and `Harness.prepare_mcp(session) -> SessionToolsets`

- [ ] **Step 1: Write the failing tests**

Append to `packages/agentbox-harness/tests/test_agent_factory.py`:

```python
def test_build_agent_uses_provided_stdio_toolsets():
    from pydantic_ai.mcp import MCPToolset

    reg = ToolRegistry()
    provided = MCPToolset("https://example.com/stdio", id="provided")
    spec = _spec(
        [
            McpToolBinding(id="local", command="python", args=["-m", "srv"]),
            McpToolBinding(server_url="https://example.com/mcp"),
        ]
    )

    agent = build_agent(
        spec,
        Mode(name="agent", flags={}),
        reg,
        TestModel(),
        stdio_toolsets=[provided],
    )

    mcp = [t for t in agent.toolsets if isinstance(t, MCPToolset)]
    assert len(mcp) == 2
    assert provided in mcp
    assert all(t is not provided for t in mcp if t.id != "provided")
```

Create `packages/agentbox-harness/tests/test_harness_mcp.py`:

```python
from agentbox_harness.harness import Harness
from agentbox_harness.session import InMemoryMessageLogStore, Session
from agentbox_harness.spec import (
    AgentSpec,
    McpToolBinding,
    Mode,
    ModelBinding,
)
from agentbox_harness.tools.mcp_session import SessionToolsets
from agentbox_harness.tools.registry import ToolRegistry
from pydantic_ai.models.test import TestModel


class FakeManager:
    def __init__(self):
        self.calls = []
        self.result = SessionToolsets()

    async def toolsets_for(self, session_id, bindings, project_root, extra_roots=None):
        self.calls.append((session_id, bindings, project_root, extra_roots))
        return self.result


def _spec() -> AgentSpec:
    return AgentSpec(
        name="coder",
        description="",
        instructions="",
        tool_bindings=[McpToolBinding(id="local", command="python")],
        model_binding=ModelBinding(model="test", provider="test"),
    )


def test_session_has_extra_roots_default():
    session = Session(
        session_id="s1",
        project_root="/tmp",
        agent_spec=None,
        store=InMemoryMessageLogStore(),
        head_id=None,
    )
    assert session.extra_roots == []


async def test_harness_prepare_mcp_uses_session_roots():
    manager = FakeManager()
    harness = Harness(
        registry=ToolRegistry(),
        model=TestModel(),
        store_factory=InMemoryMessageLogStore,
        mcp_manager=manager,
    )
    session = Session(
        session_id="s1",
        project_root="/tmp/project",
        agent_spec=_spec(),
        store=InMemoryMessageLogStore(),
        head_id=None,
        extra_roots=["/tmp/extra"],
    )

    result = await harness.prepare_mcp(session)

    assert result is manager.result
    assert manager.calls == [
        ("s1", [_spec().tool_bindings[0]], "/tmp/project", ["/tmp/extra"])
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_agent_factory.py packages/agentbox-harness/tests/test_harness_mcp.py -q`
Expected: FAIL with unexpected keyword `stdio_toolsets`, missing `extra_roots`, missing `mcp_manager`, or missing `prepare_mcp`.

- [ ] **Step 3: Implement the wiring**

Modify `session.py` `Session`:

```python
@dataclass
class Session:
    session_id: str
    project_root: str
    agent_spec: AgentSpec | None
    store: MessageLogStore
    head_id: str | None
    mode_name: str = "agent"
    extra_roots: list[str] = field(default_factory=list)
```

Add `from dataclasses import dataclass, field, replace` at the top.

Modify `agent_factory.py`:

```python
def build_agent(
    spec: AgentSpec,
    mode: Mode,
    registry: ToolRegistry,
    model: Model,
    sub_agents: dict[str, AgentSpec] | None = None,
    depth: int = 0,
    max_depth: int = 3,
    sub_session_runner=None,
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
    tools.extend(build_subagent_tools(spec, sub_agents, registry, model, depth, max_depth))
    tools.extend(build_sub_session_tools(spec, mode, sub_session_runner, session_id))
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

Import `MCPToolset` from `pydantic_ai.mcp`. Thread `stdio_toolsets` through `build_subagent_tools`:

```python
def build_subagent_tools(
    spec: AgentSpec,
    sub_agents: dict[str, AgentSpec] | None,
    registry: ToolRegistry,
    model: Model,
    depth: int = 0,
    max_depth: int = 3,
    stdio_toolsets: list[MCPToolset] | None = None,
) -> list[Callable]:
    ...
        sub_agent = build_agent(
            sub_spec,
            Mode(name="subagent", flags={}),
            registry,
            model,
            sub_agents=sub_agents,
            depth=depth + 1,
            max_depth=max_depth,
            stdio_toolsets=stdio_toolsets,
        )
```

and pass `stdio_toolsets` at the top-level call.

Modify `harness.py`:

```python
from agentbox_harness.spec import AgentSpec, McpToolBinding, Mode
from pydantic_ai.mcp import MCPToolset
from agentbox_harness.tools.mcp_session import (
    McpSessionManager,
    SessionToolsets,
    get_mcp_session_manager,
)
```

Constructor:

```python
        sub_session_runner=None,
        mcp_manager: McpSessionManager | None = None,
    ):
        ...
        self.mcp_manager = mcp_manager or get_mcp_session_manager()
```

Add:

```python
    async def prepare_mcp(self, session: Session) -> SessionToolsets:
        spec = session.agent_spec
        bindings = (
            [b for b in spec.tool_bindings if isinstance(b, McpToolBinding)]
            if spec is not None
            else []
        )
        return await self.mcp_manager.toolsets_for(
            session.session_id,
            bindings,
            session.project_root,
            session.extra_roots,
        )
```

In `run`, before `build_agent`:

```python
        session_tools = await self.prepare_mcp(session)
        agent = build_agent(
            spec,
            mode,
            self.registry,
            self.model,
            sub_agents=self.sub_agents,
            sub_session_runner=self.sub_session_runner,
            session_id=session.session_id,
            stdio_toolsets=session_tools.toolsets,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/agentbox-harness/tests/test_agent_factory.py packages/agentbox-harness/tests/test_harness_mcp.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-harness/src/agentbox_harness/session.py packages/agentbox-harness/src/agentbox_harness/agent_factory.py packages/agentbox-harness/src/agentbox_harness/harness.py packages/agentbox-harness/tests/test_agent_factory.py packages/agentbox-harness/tests/test_harness_mcp.py
git commit -m "feat(harness): use session-scoped stdio toolsets in agent runs"
```

---

### Task 5: Add the warning event and lifecycle settings

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/mcp_session.py`
- Modify: `packages/agentbox-api/src/agentbox_api/config.py`
- Modify: `packages/agentbox-api/src/agentbox_api/app.py:36-52`
- Test: `packages/agentbox-harness/tests/test_mcp_session.py`
- Test: `packages/agentbox-api/tests/test_config.py`

**Interfaces:**
- Produces: `McpWarningEvent` (`name="mcp.warning"`, fields `server`, `message`)
- Produces: Settings `mcp_idle_ttl_seconds`, `mcp_start_timeout_seconds`, `mcp_sweep_interval_seconds`

- [ ] **Step 1: Write the failing tests**

Append to `packages/agentbox-harness/tests/test_mcp_session.py`:

```python
def test_warning_event_payload():
    from agentbox_harness.tools.mcp_session import McpWarningEvent

    event = McpWarningEvent(server="srv", message="boom")
    assert event.name == "mcp.warning"
    assert event.to_payload() == {"server": "srv", "message": "boom"}
```

Append to `packages/agentbox-api/tests/test_config.py`:

```python
def test_mcp_lifecycle_defaults():
    from agentbox_api.config import Settings

    settings = Settings(jwt_secret="s" * 32)
    assert settings.mcp_idle_ttl_seconds == 1800
    assert settings.mcp_start_timeout_seconds == 30
    assert settings.mcp_sweep_interval_seconds == 60
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_mcp_session.py packages/agentbox-api/tests/test_config.py -q`
Expected: FAIL with missing `McpWarningEvent` and missing Settings fields.

- [ ] **Step 3: Implement the event and settings**

In `mcp_session.py`, add:

```python
from dataclasses import dataclass, field

from pydantic_ai.messages import CustomEvent


@dataclass(kw_only=True)
class McpWarningEvent(CustomEvent, name="mcp.warning"):
    server: str
    message: str
```

In `config.py`, add:

```python
    mcp_idle_ttl_seconds: float = 1800
    mcp_start_timeout_seconds: float = 30
    mcp_sweep_interval_seconds: float = 60
```

In `app.py` lifespan:

```python
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import asyncio
        from contextlib import suppress

        from agentbox_api.subsessions import (
            reconcile_running_sub_sessions,
            shutdown_sub_sessions,
        )
        from agentbox_harness.tools.mcp_session import get_mcp_session_manager

        configure_logging(settings)
        configure_lsp(settings)
        manager = get_mcp_session_manager()
        manager.start_timeout = settings.mcp_start_timeout_seconds

        async def sweep_loop():
            while True:
                await asyncio.sleep(settings.mcp_sweep_interval_seconds)
                await manager.sweep_idle(settings.mcp_idle_ttl_seconds)

        sweep_task = asyncio.create_task(sweep_loop())
        await reconcile_running_sub_sessions(session_factory)
        logger.info("agentbox api starting")
        try:
            yield
        finally:
            logger.info("agentbox api stopping")
            sweep_task.cancel()
            with suppress(asyncio.CancelledError):
                await sweep_task
            await manager.close_all()
            await get_lsp_manager().shutdown()
            await get_job_manager().shutdown()
            await shutdown_sub_sessions()
            await engine.dispose()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/agentbox-harness/tests/test_mcp_session.py packages/agentbox-api/tests/test_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-harness/src/agentbox_harness/tools/mcp_session.py packages/agentbox-api/src/agentbox_api/config.py packages/agentbox-api/src/agentbox_api/app.py packages/agentbox-harness/tests/test_mcp_session.py packages/agentbox-api/tests/test_config.py
git commit -m "feat(api): add MCP lifecycle settings, sweeper, and warning event"
```

---

### Task 6: Validate stdio bindings and add the agent update endpoint

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/routers/agents.py:52-68`
- Test: `packages/agentbox-api/tests/test_agents_router.py`

**Interfaces:**
- Consumes: `McpToolBinding`, `mcp_toolset_id` after Task 1
- Produces: `PUT /agents/{name}` returning `AgentSpec`
- Produces: `_to_spec` validation for transports, ids, args, env, env_passthrough

- [ ] **Step 1: Write the failing tests**

Append to `packages/agentbox-api/tests/test_agents_router.py`:

```python
async def _agent_client():
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(Provider(id="p1", name="test", kind="generic"))
        s.add(Model(id="m1", provider_id="p1", name="test-model"))
        await s.commit()
    await _seed_user_with_perms(factory, "u1", "alice", ["agents:create", "agents:read"])
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return engine, client


async def test_update_agent_round_trips_stdio_binding():
    engine, client = await _agent_client()
    try:
        token = await _login(client, "alice")
        h = {"Authorization": f"Bearer {token}"}
        r = await client.post(
            "/agents",
            json={"name": "coder", "model": "test-model"},
            headers=h,
        )
        assert r.status_code == 200

        binding = {
            "id": "time",
            "command": "uvx",
            "args": ["mcp-server-time"],
            "env": {"TZ": "UTC"},
            "env_passthrough": ["PATH"],
            "cwd": "sub",
        }
        r = await client.put(
            "/agents/coder",
            json={
                "name": "coder",
                "model": "test-model",
                "tool_bindings": [binding],
            },
            headers=h,
        )
        assert r.status_code == 200
        saved = r.json()["tool_bindings"][0]
        assert saved["id"] == "time"
        assert saved["command"] == "uvx"
        assert saved["cwd"] == "sub"
        assert saved["env_passthrough"] == ["PATH"]

        r = await client.get("/agents/coder", headers=h)
        assert r.json()["tool_bindings"][0]["command"] == "uvx"
    finally:
        await client.aclose()
        await engine.dispose()


async def test_rejects_invalid_stdio_bindings():
    engine, client = await _agent_client()
    try:
        token = await _login(client, "alice")
        h = {"Authorization": f"Bearer {token}"}
        cases = [
            {
                "name": "both",
                "model": "test-model",
                "tool_bindings": [{"id": "x", "command": "python", "server_url": "http://x"}],
            },
            {
                "name": "missing-id",
                "model": "test-model",
                "tool_bindings": [{"command": "python"}],
            },
            {
                "name": "dupe",
                "model": "test-model",
                "tool_bindings": [
                    {"id": "x", "command": "python"},
                    {"id": "x", "command": "python"},
                ],
            },
            {
                "name": "bad-env",
                "model": "test-model",
                "tool_bindings": [
                    {"id": "x", "command": "python", "env_passthrough": ["NOT-A-NAME"]}
                ],
            },
        ]
        for body in cases:
            r = await client.post("/agents", json=body, headers=h)
            assert r.status_code == 400, body["name"]
    finally:
        await client.aclose()
        await engine.dispose()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/agentbox-api/tests/test_agents_router.py -q`
Expected: FAIL with 404 for `PUT /agents/coder` and 200 for invalid cases.

- [ ] **Step 3: Implement validation and the route**

In `routers/agents.py`, replace `_to_spec` with:

```python
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_mcp_item(item: dict) -> None:
    server_url = str(item.get("server_url") or "").strip()
    command = str(item.get("command") or "").strip()
    if bool(server_url) == bool(command):
        raise ValueError("Each MCP server must set exactly one of server_url or command")
    if command:
        server_id = str(item.get("id") or "").strip()
        if not server_id:
            raise ValueError("Local MCP servers require a non-empty id")
    args = item.get("args") or []
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise ValueError("MCP args must be a list of strings")
    env = item.get("env") or {}
    if not isinstance(env, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in env.items()
    ):
        raise ValueError("MCP env must be a string-to-string object")
    passthrough = item.get("env_passthrough") or []
    if not isinstance(passthrough, list) or not all(
        isinstance(name, str) and _ENV_NAME.match(name) for name in passthrough
    ):
        raise ValueError("MCP env_passthrough entries must be valid environment variable names")


def _to_spec(body: AgentCreate) -> AgentSpec:
    bindings = []
    seen: set[str] = set()
    for b in body.tool_bindings:
        if "server_url" in b or "command" in b:
            _validate_mcp_item(b)
            binding = McpToolBinding(**b)
            server_id = mcp_toolset_id(binding)
            if server_id in seen:
                raise ValueError(f"Duplicate MCP server id: {server_id}")
            seen.add(server_id)
            bindings.append(binding)
        else:
            bindings.append(NativeToolBinding(**b))
    return AgentSpec(
        name=body.name,
        description=body.description,
        instructions=body.instructions,
        tool_bindings=bindings,
        mode_definitions=[Mode(**m) for m in body.mode_definitions],
        sub_agent_ids=body.sub_agent_ids,
        model_binding=ModelBinding(model=body.model or "", provider=""),
        model_label=body.model_label,
    )
```

Add imports `import re` and `from agentbox_harness.tools.mcp import mcp_toolset_id`.

Add the route after `create_agent`:

```python
@router.put("/{name}", response_model=AgentSpec)
async def update_agent(
    name: str,
    body: AgentCreate,
    request: Request,
    _=Depends(require_permission("agents:create")),
):
    if body.name != name:
        raise HTTPException(status_code=400, detail="Agent name cannot be changed")
    if bool(body.model) == bool(body.model_label):
        raise HTTPException(
            status_code=400,
            detail="Exactly one of model or model_label is required",
        )
    repo = AgentRepository(request.app.state.session_factory)
    try:
        spec = await repo.save(_to_spec(body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("agent updated agent={}", spec.name)
    return spec
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/agentbox-api/tests/test_agents_router.py -q`
Expected: PASS.

- [ ] **Step 5: Regenerate the OpenAPI artifacts**

```powershell
uv run python apps/web/scripts/gen-openapi.py
cd apps/web
bun run codegen
```

Expected: `openapi.json` and `schema.d.ts` include `put` for `/agents/{name}`.

- [ ] **Step 6: Commit**

```powershell
git add packages/agentbox-api/src/agentbox_api/routers/agents.py packages/agentbox-api/tests/test_agents_router.py apps/web/openapi.json apps/web/src/api/schema.d.ts
git commit -m "feat(api): validate stdio bindings and allow agent updates"
```

---

### Task 7: Support stdio servers in the MCP Apps relay

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/mcp_relay.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py:293-326`
- Test: `packages/agentbox-api/tests/test_mcp_relay.py`

**Interfaces:**
- Consumes: `McpSessionManager`, `toolsets_for`, `mcp_binding_for`
- Produces: `read_resource_for_app(manager, session_id, project_root, spec, server_id, uri, extra_roots=None)`
- Produces: `call_tool_for_app(manager, session_id, project_root, spec, server_id, name, arguments, extra_roots=None)`

- [ ] **Step 1: Write the failing test**

Append to `packages/agentbox-api/tests/test_mcp_relay.py`:

```python
async def test_relay_reads_stdio_app_resource(tmp_path, monkeypatch):
    import sys

    from agentbox_api import mcp_relay
    from agentbox_harness.spec import AgentSpec, McpToolBinding, ModelBinding
    from agentbox_harness.tools.mcp_session import McpSessionManager

    server = tmp_path / "stdio_app.py"
    server.write_text(
        "from mcp.server.mcpserver import MCPServer\n"
        "mcp = MCPServer('app')\n"
        "@mcp.resource('ui://stdio/app.html', mime_type='text/html;profile=mcp-app')\n"
        "def app() -> str:\n"
        "    return '<h1>stdio app</h1>'\n"
        "if __name__ == '__main__':\n"
        "    mcp.run(transport='stdio')\n",
        encoding="utf-8",
    )
    spec = AgentSpec(
        name="a",
        description="",
        instructions="",
        tool_bindings=[
            McpToolBinding(id="stdio-app", command=sys.executable, args=[str(server)])
        ],
        model_binding=ModelBinding(model="t", provider="t"),
    )
    manager = McpSessionManager(start_timeout=20)
    try:
        result = await mcp_relay.read_resource_for_app(
            manager, "s1", str(tmp_path), spec, "stdio-app", "ui://stdio/app.html"
        )
        assert "stdio app" in result["contents"][0]["text"]
    finally:
        await manager.close_session("s1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/agentbox-api/tests/test_mcp_relay.py -q`
Expected: FAIL because `read_resource_for_app` does not accept a manager/session/project root.

- [ ] **Step 3: Implement the relay changes**

Rewrite `mcp_relay.py`:

```python
"""Session-scoped MCP relay for MCP Apps."""

from __future__ import annotations

from typing import Any

from loguru import logger
from pydantic_ai.mcp import MCPToolset

from agentbox_harness.logging import log_exception
from agentbox_harness.spec import AgentSpec, McpToolBinding
from agentbox_harness.tools.mcp import mcp_toolset_id
from agentbox_harness.tools.mcp_session import McpSessionManager


def mcp_binding_for(spec: AgentSpec, server_id: str) -> McpToolBinding:
    for binding in spec.tool_bindings:
        if isinstance(binding, McpToolBinding) and mcp_toolset_id(binding) == server_id:
            return binding
    logger.error("mcp server not found server={}", server_id)
    raise KeyError(server_id)


async def _toolset(
    manager: McpSessionManager,
    session_id: str,
    project_root: str,
    spec: AgentSpec,
    server_id: str,
    extra_roots: list[str] | None = None,
) -> tuple[MCPToolset, bool]:
    binding = mcp_binding_for(spec, server_id)
    if binding.command:
        result = await manager.toolsets_for(
            session_id,
            [b for b in spec.tool_bindings if isinstance(b, McpToolBinding)],
            project_root,
            extra_roots,
        )
        for toolset in result.toolsets:
            if toolset.id == server_id:
                manager.touch(session_id)
                return toolset, False
        for warning in result.warnings:
            if warning.server_id == server_id:
                raise RuntimeError(warning.message)
        raise KeyError(server_id)
    return MCPToolset(binding.server_url, id=mcp_toolset_id(binding)), True


async def read_resource_for_app(
    manager: McpSessionManager,
    session_id: str,
    project_root: str,
    spec: AgentSpec,
    server_id: str,
    uri: str,
    extra_roots: list[str] | None = None,
) -> Any:
    toolset, owned = await _toolset(
        manager, session_id, project_root, spec, server_id, extra_roots
    )
    try:
        if owned:
            async with toolset:
                return await toolset.read_resource_for_app(uri)
        return await toolset.read_resource_for_app(uri)
    except Exception:
        log_exception("mcp resource read failed server={} uri={}", server_id, uri)
        raise


async def call_tool_for_app(
    manager: McpSessionManager,
    session_id: str,
    project_root: str,
    spec: AgentSpec,
    server_id: str,
    name: str,
    arguments: dict,
    extra_roots: list[str] | None = None,
) -> Any:
    toolset, owned = await _toolset(
        manager, session_id, project_root, spec, server_id, extra_roots
    )
    try:
        if owned:
            async with toolset:
                return await toolset.call_tool_for_app(name, arguments)
        return await toolset.call_tool_for_app(name, arguments)
    except Exception:
        log_exception("mcp tool call failed server={} tool={}", server_id, name)
        raise
```

In `routers/sessions.py`, change the two endpoints to load the project path and pass the manager:

```python
@router.post("/{sid}/mcp/{server_id}/resources/read")
async def read_app_resource(
    sid: str,
    server_id: str,
    body: ReadResourceBody,
    request: Request,
    _=Depends(require_permission("sessions:create")),
):
    from agentbox_api import mcp_relay
    from agentbox_harness.tools.mcp_session import get_mcp_session_manager

    spec, project_root, extra_roots = await _agent_spec_and_root(request, sid)
    try:
        return await mcp_relay.read_resource_for_app(
            get_mcp_session_manager(),
            sid,
            project_root,
            spec,
            server_id,
            body.uri,
            extra_roots,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="MCP server not found") from None
```

Change the `call_app_tool` endpoint to:

```python
@router.post("/{sid}/mcp/{server_id}/tools/call")
async def call_app_tool(
    sid: str,
    server_id: str,
    body: CallToolBody,
    request: Request,
    _=Depends(require_permission("sessions:create")),
):
    from agentbox_api import mcp_relay
    from agentbox_harness.tools.mcp_session import get_mcp_session_manager

    spec, project_root, extra_roots = await _agent_spec_and_root(request, sid)
    try:
        return await mcp_relay.call_tool_for_app(
            get_mcp_session_manager(),
            sid,
            project_root,
            spec,
            server_id,
            body.name,
            body.arguments,
            extra_roots,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="MCP server not found") from None
```

Add a helper near `_agent_spec`:

```python
async def _agent_spec_and_root(request: Request, sid: str):
    factory = request.app.state.session_factory
    async with factory() as s:
        srow = (
            await s.execute(select(SessionRow).where(SessionRow.id == sid))
        ).scalars().first()
        if srow is None:
            raise HTTPException(status_code=404, detail="Session not found")
        project = await s.get(Project, srow.project_id)
    spec = await _agent_spec(request, sid)
    return spec, project.path if project is not None else "", (
        project.extra_roots if project is not None else []
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/agentbox-api/tests/test_mcp_relay.py packages/agentbox-api/tests/test_mcp_apps.py -q`
Expected: PASS. Existing HTTP relay tests must still pass.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-api/src/agentbox_api/mcp_relay.py packages/agentbox-api/src/agentbox_api/routers/sessions.py packages/agentbox-api/tests/test_mcp_relay.py
git commit -m "feat(api): relay MCP Apps through session-scoped stdio servers"
```

---

### Task 8: Surface MCP warnings in the web chat stream

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py:453-524`
- Modify: `apps/web/src/chat/useChat.ts:15-24,96-203`
- Test: `apps/web/src/chat/useChat.test.tsx`

**Interfaces:**
- Consumes: `McpWarningEvent`, `Harness.prepare_mcp`
- Produces: AG-UI custom event `mcp.warning` with `{server, message}`
- Produces: `useChat` notification on custom warnings

- [ ] **Step 1: Write the failing frontend test**

Create `apps/web/src/chat/useChat.test.tsx`:

```tsx
import { notifications } from "@mantine/notifications";
import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { useChat } from "./useChat";

vi.mock("./agent", () => ({
  streamChat: async function* () {
    yield { type: "CUSTOM", name: "mcp.warning", value: { server: "time", message: "boom" } };
    yield { type: "RUN_FINISHED" };
  },
}));

vi.mock("@mantine/notifications", () => ({ notifications: { show: vi.fn() } }));

describe("useChat MCP warnings", () => {
  test("shows a notification and finishes the run", async () => {
    const { result } = renderHook(() => useChat("http://test", null, "s1"));
    await act(async () => {
      await result.current.send("hi", {} as never);
    });
    await waitFor(() =>
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({ message: expect.stringContaining("boom") }),
      ),
    );
    expect(result.current.error).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && bun run test -- src/chat/useChat.test.tsx`
Expected: FAIL because `CUSTOM` events are ignored.

- [ ] **Step 3: Implement the event and the handler**

In `routers/sessions.py`, after `harness` is constructed and `session` exists, call `warnings = (await harness.prepare_mcp(session)).warnings`. Then at the start of `raw_events()`:

```python
    from agentbox_harness.events import RunEvent
    from agentbox_harness.tools.mcp_session import McpWarningEvent

    async def raw_events():
        for index, warning in enumerate(warnings):
            yield RunEvent(
                run_id="mcp",
                seq=-(index + 1),
                event=McpWarningEvent(
                    server=warning.server_id, message=warning.message
                ),
            )

        async def finish():
            ...
```

Keep the rest of the generator unchanged. The `RunEvent` construction needs the exact dataclass fields; use `run_id`, `seq`, `event`.

In `useChat.ts`:

Add to `RawEvent`:

```ts
  name?: string;
  value?: unknown;
```

Add an import:

```ts
import { notifications } from "@mantine/notifications";
```

Add a case:

```ts
      case EventType.CUSTOM: {
        if (event.name === "mcp.warning") {
          const payload = (event.value ?? {}) as { server?: string; message?: string };
          notifications.show({
            title: `MCP server: ${payload.server ?? "unknown"}`,
            message: payload.message ?? "Server unavailable",
            color: "yellow",
          });
        }
        break;
      }
```

Ensure `EventType.CUSTOM` is the exact enum member exported by `@ag-ui/core` (the same package already supplies the other members).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && bun run test -- src/chat/useChat.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-api/src/agentbox_api/routers/sessions.py apps/web/src/chat/useChat.ts apps/web/src/chat/useChat.test.tsx
git commit -m "feat(chat): show MCP server warnings as notifications"
```

---

### Task 9: Build the structured MCP editor and validation

**Files:**
- Create: `apps/web/src/pages/agents/mcpTypes.ts`
- Modify: `apps/web/src/pages/agents/AgentMcpEditor.tsx`
- Modify: `apps/web/src/pages/agents/agentFormValidation.ts`
- Test: `apps/web/src/pages/agents/mcpTypes.test.ts`
- Test: `apps/web/src/pages/agents/AgentMcpEditor.test.tsx`

**Interfaces:**
- Produces: `McpServerDraft`
- Produces: `emptyMcpServer()`, `fromBinding(binding)`, `toBinding(draft)`, `validateMcpServers(drafts)`
- Produces: `AgentMcpEditor` with `value: McpServerDraft[]`, `onChange(drafts)`, `error?: string`

- [ ] **Step 1: Write the failing tests**

Create `apps/web/src/pages/agents/mcpTypes.test.ts`:

```ts
import { describe, expect, test } from "vitest";

import { fromBinding, toBinding, validateMcpServers } from "./mcpTypes";

describe("mcpTypes", () => {
  test("round-trips a stdio binding", () => {
    const draft = fromBinding({
      id: "time",
      command: "uvx",
      args: ["mcp-server-time"],
      env: { TZ: "UTC" },
      env_passthrough: ["PATH"],
      cwd: "sub",
    });
    expect(draft?.kind).toBe("stdio");
    expect(toBinding(draft!)).toEqual({
      id: "time",
      command: "uvx",
      args: ["mcp-server-time"],
      env: { TZ: "UTC" },
      env_passthrough: ["PATH"],
      cwd: "sub",
    });
  });

  test("round-trips a remote binding", () => {
    const draft = fromBinding({ id: "app", server_url: "https://x/mcp" });
    expect(draft?.kind).toBe("remote");
    expect(toBinding(draft!)).toEqual({ id: "app", server_url: "https://x/mcp" });
  });

  test("rejects duplicate stdio ids", () => {
    const base = fromBinding({ id: "a", command: "python" })!;
    const error = validateMcpServers([base, { ...base }]);
    expect(error).toContain("unique");
  });
});
```

Create `apps/web/src/pages/agents/AgentMcpEditor.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { AgentMcpEditor } from "./AgentMcpEditor";
import { emptyMcpServer } from "./mcpTypes";

describe("AgentMcpEditor", () => {
  test("adds and reports a stdio server", () => {
    const onChange = vi.fn();
    render(<AgentMcpEditor value={[emptyMcpServer()]} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("MCP name 1"), { target: { value: "time" } });
    fireEvent.change(screen.getByLabelText("MCP command 1"), { target: { value: "uvx" } });
    fireEvent.change(screen.getByLabelText("MCP args 1"), {
      target: { value: "mcp-server-time" },
    });
    expect(onChange).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/web && bun run test -- src/pages/agents/mcpTypes.test.ts src/pages/agents/AgentMcpEditor.test.tsx`
Expected: FAIL because `mcpTypes` does not exist and the editor has the old props.

- [ ] **Step 3: Implement the types and editor**

Create `apps/web/src/pages/agents/mcpTypes.ts`:

```ts
export type McpServerDraft = {
  id: string;
  kind: "remote" | "stdio";
  server_url: string;
  command: string;
  args: string;
  env: { name: string; value: string }[];
  envPassthrough: string;
  cwd: string;
};

export function emptyMcpServer(): McpServerDraft {
  return {
    id: "",
    kind: "remote",
    server_url: "",
    command: "",
    args: "",
    env: [],
    envPassthrough: "",
    cwd: "",
  };
}

export function fromBinding(binding: Record<string, unknown>): McpServerDraft | null {
  const isStdio = typeof binding.command === "string" && binding.command !== "";
  if (!isStdio && typeof binding.server_url !== "string") return null;
  const env = (binding.env as Record<string, string> | undefined) ?? {};
  const passthrough = (binding.env_passthrough as string[] | undefined) ?? [];
  const args = (binding.args as string[] | undefined) ?? [];
  return {
    id: String(binding.id ?? ""),
    kind: isStdio ? "stdio" : "remote",
    server_url: String(binding.server_url ?? ""),
    command: String(binding.command ?? ""),
    args: args.join("\n"),
    env: Object.entries(env).map(([name, value]) => ({ name, value: String(value) })),
    envPassthrough: passthrough.join(", "),
    cwd: String(binding.cwd ?? ""),
  };
}

function splitArgs(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function splitNames(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((name) => name.trim())
    .filter(Boolean);
}

export function toBinding(draft: McpServerDraft): Record<string, unknown> {
  const id = draft.id.trim();
  if (draft.kind === "remote") {
    return id ? { id, server_url: draft.server_url.trim() } : { server_url: draft.server_url.trim() };
  }
  const env = Object.fromEntries(
    draft.env.filter((row) => row.name.trim()).map((row) => [row.name.trim(), row.value]),
  );
  return {
    id,
    command: draft.command.trim(),
    args: splitArgs(draft.args),
    env,
    env_passthrough: splitNames(draft.envPassthrough),
    cwd: draft.cwd.trim(),
  };
}

const ENV_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

export function validateMcpServers(drafts: McpServerDraft[]): string | null {
  const ids: string[] = [];
  for (const draft of drafts) {
    const id = draft.id.trim();
    if (draft.kind === "stdio" && !id) return "Local MCP servers need a name.";
    if (id) ids.push(id);
    if (draft.kind === "remote") {
      try {
        const url = new URL(draft.server_url.trim());
        if (url.protocol !== "http:" && url.protocol !== "https:") {
          return "MCP URLs must use http or https.";
        }
      } catch {
        return "Enter a valid http/https MCP URL.";
      }
    } else if (!draft.command.trim()) {
      return "Local MCP servers need a command.";
    }
    for (const row of draft.env) {
      if (row.name.trim() && !ENV_NAME.test(row.name.trim())) {
        return `Invalid env name: ${row.name}`;
      }
    }
    for (const name of splitNames(draft.envPassthrough)) {
      if (!ENV_NAME.test(name)) return `Invalid env passthrough name: ${name}`;
    }
  }
  if (new Set(ids).size !== ids.length) return "MCP server names must be unique.";
  return null;
}
```

Rewrite `AgentMcpEditor.tsx` with one card per draft:

```tsx
import { RiAddLine, RiDeleteBin6Line } from "@remixicon/react";

import { TextInput } from "../../design-system/forms/TextInput";
import { Button } from "../../design-system/primitives/Button";
import { HelpTip } from "../../help/HelpTip";
import { emptyMcpServer, type McpServerDraft } from "./mcpTypes";

const update = (
  value: McpServerDraft[],
  index: number,
  patch: Partial<McpServerDraft>,
): McpServerDraft[] => value.map((item, i) => (i === index ? { ...item, ...patch } : item));

export function AgentMcpEditor({
  value,
  onChange,
  error,
}: {
  value: McpServerDraft[];
  onChange: (servers: McpServerDraft[]) => void;
  error?: string;
}) {
  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div style={{ alignItems: "center", display: "flex", gap: 8 }}>
        <strong>MCP servers</strong>
        <HelpTip id="agent.mcp" />
      </div>
      {value.map((server, index) => (
        <div key={index} style={{ border: "1px solid var(--ab-border)", display: "grid", gap: 8, padding: 12 }}>
          <div style={{ display: "flex", gap: 8 }}>
            <select
              aria-label={`MCP transport ${index + 1}`}
              value={server.kind}
              onChange={(event) =>
                onChange(update(value, index, { kind: event.currentTarget.value as "remote" | "stdio" }))
              }
            >
              <option value="remote">Remote URL</option>
              <option value="stdio">Local command</option>
            </select>
            <TextInput
              aria-label={`MCP name ${index + 1}`}
              placeholder="Name"
              value={server.id}
              onChange={(event) => onChange(update(value, index, { id: event.currentTarget.value }))}
              style={{ flex: 1 }}
            />
            <Button
              size="compact-sm"
              variant="subtle"
              color="red"
              onClick={() => onChange(value.filter((_, i) => i !== index))}
            >
              <RiDeleteBin6Line size={16} />
            </Button>
          </div>
          {server.kind === "remote" ? (
            <TextInput
              aria-label={`MCP URL ${index + 1}`}
              placeholder="https://server/mcp"
              value={server.server_url}
              onChange={(event) =>
                onChange(update(value, index, { server_url: event.currentTarget.value }))
              }
            />
          ) : (
            <>
              <TextInput
                aria-label={`MCP command ${index + 1}`}
                placeholder="uvx"
                value={server.command}
                onChange={(event) =>
                  onChange(update(value, index, { command: event.currentTarget.value }))
                }
              />
              <textarea
                aria-label={`MCP args ${index + 1}`}
                placeholder="One argument per line"
                value={server.args}
                onChange={(event) =>
                  onChange(update(value, index, { args: event.currentTarget.value }))
                }
              />
              <TextInput
                aria-label={`MCP cwd ${index + 1}`}
                placeholder="cwd (defaults to project root)"
                value={server.cwd}
                onChange={(event) =>
                  onChange(update(value, index, { cwd: event.currentTarget.value }))
                }
              />
            </>
          )}
          <p style={{ color: "var(--ab-text-muted)", fontSize: 12, margin: 0 }}>
            Local commands run on this machine; cwd is sandboxed to the project and its extra roots.
          </p>
        </div>
      ))}
      <Button variant="light" onClick={() => onChange([...value, emptyMcpServer()])}>
        <RiAddLine size={16} /> Add MCP server
      </Button>
      {error && (
        <span role="alert" style={{ color: "var(--ab-danger)" }}>
          {error}
        </span>
      )}
    </div>
  );
}
```

Keep the env rows UI available for local servers by rendering two `TextInput`s per env row plus a passthrough input. Use these labels so tests can find them:

```tsx
{server.kind === "stdio" && (
  <>
    {server.env.map((row, rowIndex) => (
      <div key={rowIndex} style={{ display: "flex", gap: 8 }}>
        <TextInput
          aria-label={`MCP env name ${index + 1}-${rowIndex + 1}`}
          placeholder="NAME"
          value={row.name}
          onChange={(event) => {
            const env = server.env.map((item, i) =>
              i === rowIndex ? { ...item, name: event.currentTarget.value } : item,
            );
            onChange(update(value, index, { env }));
          }}
        />
        <TextInput
          aria-label={`MCP env value ${index + 1}-${rowIndex + 1}`}
          placeholder="value"
          type="password"
          value={row.value}
          onChange={(event) => {
            const env = server.env.map((item, i) =>
              i === rowIndex ? { ...item, value: event.currentTarget.value } : item,
            );
            onChange(update(value, index, { env }));
          }}
        />
      </div>
    ))}
    <Button
      variant="light"
      size="compact-sm"
      onClick={() =>
        onChange(update(value, index, { env: [...server.env, { name: "", value: "" }] }))
      }
    >
      Add env
    </Button>
    <TextInput
      aria-label={`MCP env passthrough ${index + 1}`}
      placeholder="Host env names, comma separated"
      value={server.envPassthrough}
      onChange={(event) =>
        onChange(update(value, index, { envPassthrough: event.currentTarget.value }))
      }
    />
  </>
)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && bun run test -- src/pages/agents/mcpTypes.test.ts src/pages/agents/AgentMcpEditor.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/pages/agents/mcpTypes.ts apps/web/src/pages/agents/AgentMcpEditor.tsx apps/web/src/pages/agents/mcpTypes.test.ts apps/web/src/pages/agents/AgentMcpEditor.test.tsx
git commit -m "feat(web): add structured MCP server editor"
```

---

### Task 10: Add the create/edit agent drawer and update client

**Files:**
- Create: `apps/web/src/pages/agents/AgentFormDrawer.tsx`
- Delete: `apps/web/src/pages/agents/AgentCreateDrawer.tsx`
- Modify: `apps/web/src/api/endpoints.ts:203-223`
- Modify: `apps/web/src/api/queries.ts:191-205`
- Modify: `apps/web/src/pages/AgentsPage.tsx:1-84`
- Modify: `apps/web/src/pages/agents/AgentList.tsx:1-165`
- Test: `apps/web/src/pages/agents/AgentFormDrawer.test.tsx`

**Interfaces:**
- Consumes: `McpServerDraft`, `fromBinding`, `toBinding`, `validateMcpServers`, generated `PUT` client
- Produces: `updateAgent(name, body)` and `useUpdateAgent()`
- Produces: `AgentFormDrawer({ opened, onClose, agent?: Agent, subAgentOptions })`

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/pages/agents/AgentFormDrawer.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { AgentFormDrawer } from "./AgentFormDrawer";

vi.mock("../../api/queries", () => ({
  useCreateAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useLabels: () => ({ data: [] }),
  useModels: () => ({ data: [] }),
  useProviders: () => ({ data: [] }),
  useUploadAvatar: () => ({ mutateAsync: vi.fn() }),
}));

describe("AgentFormDrawer", () => {
  test("prefills an existing agent for editing", () => {
    render(
      <AgentFormDrawer
        opened
        onClose={() => undefined}
        subAgentOptions={[]}
        agent={{
          name: "coder",
          description: "desc",
          instructions: "inst",
          model_binding: { model: "m", provider: "p" },
          model_label: null,
          tool_bindings: [{ id: "time", command: "uvx", args: ["mcp-server-time"] }],
          mode_definitions: [{ name: "agent", flags: { write: true } }],
          sub_agent_ids: [],
        }}
      />,
    );
    expect(screen.getByDisplayValue("coder")).toBeDisabled();
    expect(screen.getByDisplayValue("uvx")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && bun run test -- src/pages/agents/AgentFormDrawer.test.tsx`
Expected: FAIL because `AgentFormDrawer` does not exist.

- [ ] **Step 3: Implement the client, drawer, and list action**

In `endpoints.ts`:

```ts
export async function updateAgent(
  name: string,
  body: {
    name: string;
    description: string;
    instructions: string;
    model?: string;
    model_label?: string;
    tool_bindings: Record<string, unknown>[];
    mode_definitions: Record<string, unknown>[];
    sub_agent_ids: string[];
  },
): Promise<Agent> {
  const { data, error, response } = await api.PUT("/agents/{name}", {
    params: { path: { name } },
    body,
  });
  if (error || !response.ok) throw toApiError(error, "Failed to update agent", response.status);
  return data as Agent;
}
```

In `queries.ts` import `updateAgent` and add:

```ts
export function useUpdateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, body }: { name: string; body: Parameters<typeof updateAgent>[1] }) =>
      updateAgent(name, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}
```

Create `AgentFormDrawer.tsx` from the existing `AgentCreateDrawer.tsx` with these changes:

- Props: `{ opened, onClose, subAgentOptions, agent?: Agent }`.
- Initialize state from `agent`:

```tsx
  const editing = agent !== undefined;
  const [name, setName] = useState(agent?.name ?? "");
  const [description, setDescription] = useState(agent?.description ?? "");
  const [instructions, setInstructions] = useState(agent?.instructions ?? "");

  const initialModelRef = (() => {
    if (!agent) return null;
    if (agent.model_label) return `label:${agent.model_label}`;
    const match = models?.find((model) => model.name === agent.model_binding.model);
    return `model:${match?.id ?? agent.model_binding.model}`;
  })();
  const [modelRef, setModelRef] = useState<string | null>(initialModelRef);

  const nativeNames =
    agent?.tool_bindings
      ?.filter((binding) => !("server_url" in binding) && !("command" in binding))
      .map((binding) => ("name" in binding ? String(binding.name) : ""))
      .filter(Boolean) ?? [];
  const [tools, setTools] = useState<string[]>([
    ...nativeNames.filter((item) => !TERMINAL_TOOLS.includes(item)),
    ...(nativeNames.some((item) => TERMINAL_TOOLS.includes(item)) ? ["terminal"] : []),
  ]);
  const [mcpServers, setMcpServers] = useState<McpServerDraft[]>(
    agent?.tool_bindings
      ?.map((binding) => fromBinding(binding as Record<string, unknown>))
      .filter((draft): draft is McpServerDraft => draft !== null) ?? [],
  );
```

Add the import at the top of the drawer:

```tsx
import { TERMINAL_TOOLS } from "../AgentsPage";
```

When editing, keep the current model selectable even if the models query has not resolved yet by appending a fallback option:

```tsx
  const modelOptions = [
    ...(models ?? []).map((model) => ({
      value: `model:${model.id}`,
      label: `${providerName(model.provider_id)} · ${model.name}`,
    })),
    ...(agent && !agent.model_label &&
    !(models ?? []).some((model) => model.name === agent.model_binding.model)
      ? [{ value: `model:${agent.model_binding.model}`, label: agent.model_binding.model }]
      : []),
    ...(labels ?? []).map((label) => ({
      value: `label:${label.name}`,
      label: `label: ${label.name}`,
    })),
  ];
```

- `onSubmit` calls `update.mutateAsync({ name, body })` in edit mode and `create.mutateAsync(body)` in create mode; build `tool_bindings` from native tools plus `mcpServers.map(toBinding)`.
- Name field: `disabled={editing}`.
- Validate MCP with `validateMcpServers(mcpServers)` and set a `mcp` error.
- Button label: `editing ? "Save agent" : "Create agent"`.

Update `AgentsPage.tsx`:

```tsx
  const [editor, setEditor] = useState<{ mode: "create" } | { mode: "edit"; agent: Agent } | null>(null);
  ...
      <AgentList
        agents={agentList}
        onNew={() => setEditor({ mode: "create" })}
        onEdit={(agent) => setEditor({ mode: "edit", agent })}
      />
      <AgentFormDrawer
        opened={editor !== null}
        onClose={() => setEditor(null)}
        agent={editor?.mode === "edit" ? editor.agent : undefined}
        subAgentOptions={agentList.map((item) => item.name)}
      />
```

Update `AgentList.tsx` props with `onEdit: (agent: Agent) => void` and add an edit icon button before Delete:

```tsx
                <IconButton
                  label="Edit"
                  icon={RiEditLine}
                  size={16}
                  onClick={() => onEdit(agent)}
                />
```

Import `RiEditLine` from `@remixicon/react`.

Delete `AgentCreateDrawer.tsx`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && bun run test -- src/pages/agents/AgentFormDrawer.test.tsx src/pages/AgentsPage.test.tsx`
Expected: PASS. If `AgentsPage.test.tsx` needs the new `onEdit` prop in a mock, add it.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/pages/agents/AgentFormDrawer.tsx apps/web/src/pages/agents/AgentCreateDrawer.tsx apps/web/src/api/endpoints.ts apps/web/src/api/queries.ts apps/web/src/pages/AgentsPage.tsx apps/web/src/pages/agents/AgentList.tsx apps/web/src/pages/agents/AgentFormDrawer.test.tsx
git commit -m "feat(web): create and edit agents with stdio MCP servers"
```

---

### Task 11: Wire ACP, A2A, sub-sessions, and session deletion

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/acp_server.py:182-189,254-260,282-292,416-424,452-463`
- Modify: `packages/agentbox-api/src/agentbox_api/a2a_executor.py:124-141`
- Modify: `packages/agentbox-api/src/agentbox_api/subsessions.py:163-180`
- Modify: `packages/agentbox-api/src/agentbox_api/runtime.py:143-151`
- Test: `packages/agentbox-api/tests/test_acp_stdio.py`
- Test: `packages/agentbox-api/tests/test_terminal_wiring.py`

**Interfaces:**
- Consumes: `get_mcp_session_manager()`, `Harness.prepare_mcp`
- Produces: session `extra_roots` populated for ACP, A2A, and sub-sessions
- Produces: `delete_session_data` closes MCP entries

- [ ] **Step 1: Write the failing tests**

Append to `packages/agentbox-api/tests/test_terminal_wiring.py`:

```python
async def test_delete_session_data_closes_mcp(monkeypatch):
    from agentbox_harness.tools.mcp_session import get_mcp_session_manager

    closed: list[str] = []

    async def fake_close(session_id):
        closed.append(session_id)

    monkeypatch.setattr(
        "agentbox_harness.tools.mcp_session.McpSessionManager.close_session",
        fake_close,
    )
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    await delete_session_data(factory, "s1")
    assert "s1" in closed
    await engine.dispose()
```

Append to `packages/agentbox-api/tests/test_acp_stdio.py`:

```python
async def test_acp_close_session_stops_mcp_manager(monkeypatch):
    from agentbox_harness.tools.mcp_session import McpSessionManager

    closed: list[str] = []

    async def fake_close(self, session_id):
        closed.append(session_id)

    class FakeJobs:
        async def kill_session(self, session_id):
            return None

    async def fake_cancel_sub_sessions(factory, session_id):
        return None

    monkeypatch.setattr(McpSessionManager, "close_session", fake_close)
    monkeypatch.setattr(
        "agentbox_api.acp_server.get_job_manager", lambda: FakeJobs()
    )
    monkeypatch.setattr(
        "agentbox_api.subsessions.cancel_sub_sessions", fake_cancel_sub_sessions
    )

    from agentbox_api.acp_server import AgentboxAcpAgent

    agent = AgentboxAcpAgent("acp-test", None, None)
    await agent.close_session("s1")
    assert "s1" in closed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/agentbox-api/tests/test_terminal_wiring.py packages/agentbox-api/tests/test_acp_stdio.py -q`
Expected: FAIL because deletion and ACP close do not close the manager.

- [ ] **Step 3: Implement the wiring**

In `runtime.py` `delete_session_data`, before deleting rows:

```python
    from agentbox_harness.tools.mcp_session import get_mcp_session_manager

    await get_mcp_session_manager().close_session(session_id)
```

In `acp_server.py` `AgentboxAcpAgent.__init__`, store the manager:

```python
        from agentbox_harness.tools.mcp_session import get_mcp_session_manager

        self.mcp_manager = get_mcp_session_manager()
```

Pass `extra_roots` into the ACP `Session` (inside `prompt`):

```python
            extra_roots=project.extra_roots,
```

`prompt` currently only has `sess.project_root`; load the project's extra roots into `AcpSession` or load them in `prompt`. Add `extra_roots: list[str] = field(default_factory=list)` as the last field of `AcpSession` so existing positional constructor calls keep working. Pass `extra_roots=project.extra_roots` as a keyword in both `AcpSession(...)` calls (`new_session` and `_restore`), and pass `extra_roots=sess.extra_roots` to `Session`. Import `field` from `dataclasses` in `acp_server.py`.

In `acp_server.py` `prompt`, after constructing `harness`, call:

```python
        warnings = (await harness.prepare_mcp(session)).warnings
        for warning in warnings:
            logger.warning(
                "acp mcp server unavailable session={} server={} error={}",
                session_id,
                warning.server_id,
                warning.message,
            )
```

In `close_session`:

```python
        await self.mcp_manager.close_session(session_id)
```

In `_serve`, after `configure_lsp(settings)`, apply the configured timeout:

```python
    from agentbox_harness.tools.mcp_session import get_mcp_session_manager

    get_mcp_session_manager().start_timeout = settings.mcp_start_timeout_seconds
```

In `a2a_executor.py`, add `extra_roots=project.extra_roots if project is not None else []` to the `Session` constructor and log warnings after constructing the harness:

```python
        warnings = (await harness.prepare_mcp(session)).warnings
        for warning in warnings:
            logger.warning(
                "a2a mcp server unavailable session={} server={} error={}",
                session_id,
                warning.server_id,
                warning.message,
            )
```

In `subsessions.py`, add `extra_roots=self._context.extra_roots` to the child `Session`, and after constructing the harness:

```python
        warnings = (await harness.prepare_mcp(session)).warnings
        for warning in warnings:
            logger.warning(
                "sub-session mcp server unavailable session={} server={} error={}",
                child_id,
                warning.server_id,
                warning.message,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/agentbox-api/tests/test_terminal_wiring.py packages/agentbox-api/tests/test_acp_stdio.py packages/agentbox-api/tests/test_acp.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-api/src/agentbox_api/acp_server.py packages/agentbox-api/src/agentbox_api/a2a_executor.py packages/agentbox-api/src/agentbox_api/subsessions.py packages/agentbox-api/src/agentbox_api/runtime.py packages/agentbox-api/tests/test_acp_stdio.py packages/agentbox-api/tests/test_terminal_wiring.py
git commit -m "feat(api): share the MCP session manager across ACP, A2A, and sub-sessions"
```

---

### Task 12: Add web-chat integration and cleanup tests

**Files:**
- Test: `packages/agentbox-api/tests/test_stdio_mcp.py`

**Interfaces:**
- Consumes: `PUT /agents/{name}`, `POST /sessions/{sid}/messages`, the stdio manager
- Produces: coverage for reuse across turns, warning custom events, and session deletion cleanup

- [ ] **Step 1: Write the failing tests**

Create `packages/agentbox-api/tests/test_stdio_mcp.py`:

```python
import pathlib
import sys

import httpx
import pytest

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.security import hash_password
from agentbox_harness.tools.mcp_session import get_mcp_session_manager
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.auth import (
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)
from agentbox_models.tables.core import Agent, Model, Project, Provider, SessionRow

SERVER = pathlib.Path(__file__).with_name("stdio_app_server.py")


async def _setup(tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(
            User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw"))
        )
        s.add(Role(id="r_u1", name="role"))
        for i, p in enumerate(["sessions:create", "sessions:read", "agents:create", "agents:read"]):
            s.add(Permission(id=f"p{i}_u1", name=p))
            s.add(RolePermissionLink(role_id="r_u1", permission_id=f"p{i}_u1"))
        s.add(UserRoleLink(user_id="u1", role_id="r_u1"))
        s.add(Provider(id="prov", name="test", kind="test"))
        s.add(Model(id="m", provider_id="prov", name="test-model"))
        s.add(
            Agent(
                id="ag",
                name="agent",
                description="d",
                instructions="i",
                model_id="m",
                tool_bindings="[]",
                mode_definitions='[{"name":"agent","flags":{"write":true}}]',
                sub_agent_ids="[]",
            )
        )
        s.add(Project(id="prj", name="p", path=str(tmp_path), owner_id="u1"))
        s.add(SessionRow(id="s1", project_id="prj", agent_id="ag"))
        await s.commit()
    app = create_app(Settings(jwt_secret="s" * 32), engine=engine, session_factory=factory)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    return engine, client


async def _login(client) -> dict[str, str]:
    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_stdio_server_is_reused_across_turns(tmp_path):
    engine, client = await _setup(tmp_path)
    try:
        h = await _login(client)
        r = await client.put(
            "/agents/agent",
            json={
                "name": "agent",
                "model": "test-model",
                "tool_bindings": [
                    {
                        "id": "echo",
                        "command": sys.executable,
                        "args": [str(SERVER)],
                    }
                ],
            },
            headers=h,
        )
        assert r.status_code == 200

        await client.post("/sessions/s1/messages", json={"content": "hi"}, headers=h)
        first = get_mcp_session_manager()._entries["s1"].toolsets[0]
        await client.post("/sessions/s1/messages", json={"content": "again"}, headers=h)
        second = get_mcp_session_manager()._entries["s1"].toolsets[0]
        assert first is second
    finally:
        await get_mcp_session_manager().close_all()
        await client.aclose()
        await engine.dispose()


async def test_broken_server_emits_warning_and_run_succeeds(tmp_path):
    engine, client = await _setup(tmp_path)
    try:
        h = await _login(client)
        r = await client.put(
            "/agents/agent",
            json={
                "name": "agent",
                "model": "test-model",
                "tool_bindings": [
                    {"id": "broken", "command": "definitely-not-a-real-command-xyz"}
                ],
            },
            headers=h,
        )
        assert r.status_code == 200

        r = await client.post(
            "/sessions/s1/messages", json={"content": "hi"}, headers=h
        )
        assert r.status_code == 200
        assert "mcp.warning" in r.text
        assert "broken" in r.text
    finally:
        await get_mcp_session_manager().close_all()
        await client.aclose()
        await engine.dispose()


async def test_delete_session_closes_mcp_process(tmp_path):
    engine, client = await _setup(tmp_path)
    try:
        h = await _login(client)
        await client.put(
            "/agents/agent",
            json={
                "name": "agent",
                "model": "test-model",
                "tool_bindings": [
                    {"id": "echo", "command": sys.executable, "args": [str(SERVER)]}
                ],
            },
            headers=h,
        )
        await client.post("/sessions/s1/messages", json={"content": "hi"}, headers=h)
        assert "s1" in get_mcp_session_manager()._entries
        r = await client.delete("/sessions/s1", headers=h)
        assert r.status_code == 200
        assert "s1" not in get_mcp_session_manager()._entries
    finally:
        await get_mcp_session_manager().close_all()
        await client.aclose()
        await engine.dispose()
```

Create `packages/agentbox-api/tests/stdio_app_server.py`:

```python
"""A minimal real stdio MCP server for API integration tests."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("agentbox-test-api-stdio")


@mcp.tool()
def echo(text: str) -> str:
    """Echo text back."""
    return f"echo:{text}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/agentbox-api/tests/test_stdio_mcp.py -q`
Expected: FAIL until the manager wiring, warning event, and delete hook are complete.

- [ ] **Step 3: Implement any remaining wiring**

If the tests fail, verify these pieces exist:

- `routers/sessions.py` calls `harness.prepare_mcp(session)` and injects `McpWarningEvent`s.
- `runtime.delete_session_data` calls `close_session`.
- `Session` construction in the web chat path passes `extra_roots`:

```python
    session = Session(
        session_id=sid,
        project_root=project.path,
        agent_spec=spec,
        store=store,
        head_id=None,
        mode_name=body.mode or "agent",
        extra_roots=project.extra_roots,
    )
```

- The `AgentRepository` parser accepts the new fields (it already builds `McpToolBinding(**item)`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/agentbox-api/tests/test_stdio_mcp.py -q`
Expected: PASS. Tests use the local `stdio_app_server.py`; no network.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-api/tests/test_stdio_mcp.py packages/agentbox-api/tests/stdio_app_server.py packages/agentbox-api/src/agentbox_api/routers/sessions.py packages/agentbox-api/src/agentbox_api/runtime.py
git commit -m "test(api): cover session-scoped stdio MCP lifecycle"
```

---

### Task 13: Add the real `uvx mcp-server-time` integration test

**Files:**
- Test: `packages/agentbox-harness/tests/test_mcp_time.py`

**Interfaces:**
- Consumes: `McpSessionManager`, `McpToolBinding(id="time", command="uvx", args=["mcp-server-time"])`
- Produces: external integration coverage for a real third-party stdio server

- [ ] **Step 1: Write the test**

Create `packages/agentbox-harness/tests/test_mcp_time.py`:

```python
import asyncio
import shutil

import pytest

from agentbox_harness.spec import McpToolBinding
from agentbox_harness.tools.mcp_session import McpSessionManager


@pytest.mark.timeout(120)
async def test_uvx_mcp_server_time_lifecycle(tmp_path):
    if shutil.which("uvx") is None:
        pytest.skip("uvx is not installed")

    manager = McpSessionManager(start_timeout=90)
    binding = McpToolBinding(
        id="time",
        command="uvx",
        args=["mcp-server-time"],
        cwd="",
    )
    try:
        result = await manager.toolsets_for("s1", [binding], str(tmp_path))
        if result.warnings:
            pytest.skip(f"uvx mcp-server-time unavailable: {result.warnings[0].message}")
        assert len(result.toolsets) == 1
        toolset = result.toolsets[0]

        tools = await asyncio.wait_for(toolset.list_tools(), timeout=30)
        names = {tool.name for tool in tools}
        assert any(name.endswith("get_current_time") for name in names)

        current = await asyncio.wait_for(
            toolset.call_tool_for_app(
                next(name for name in names if name.endswith("get_current_time")),
                {"timezone": "UTC"},
            ),
            timeout=30,
        )
        assert current

        again = await manager.toolsets_for("s1", [binding], str(tmp_path))
        assert again.toolsets[0] is toolset
        assert len(manager._entries["s1"].toolsets) == 1
    finally:
        await manager.close_session("s1")
    assert "s1" not in manager._entries
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest packages/agentbox-harness/tests/test_mcp_time.py -q`
Expected: PASS after `uvx` fetches `mcp-server-time`, or SKIP with a clear reason when `uvx` or the package fetch is unavailable.

- [ ] **Step 3: Commit**

```powershell
git add packages/agentbox-harness/tests/test_mcp_time.py
git commit -m "test(harness): exercise uvx mcp-server-time stdio lifecycle"
```

---

### Task 14: Update help, roadmap, and run full verification

**Files:**
- Modify: `apps/web/src/help/content.ts:133-150`
- Modify: `docs/ROADMAP.md:18`
- Modify: `docs/ROADMAP.md:185-222` (add spec/plan row)
- Verify: all packages and frontend

**Interfaces:**
- Consumes: everything above

- [ ] **Step 1: Update the help content**

Replace the `agent.mcp` entry with:

```ts
  "agent.mcp": {
    id: "agent.mcp",
    title: "MCP servers",
    summary:
      "MCP servers add tools and apps, either from a remote endpoint or a local command.",
    sections: [
      {
        heading: "Remote URL",
        paragraphs: [
          "Enter the HTTP or HTTPS URL for a remote MCP server. Authentication and transport settings belong to the server.",
        ],
      },
      {
        heading: "Local command",
        paragraphs: [
          "A local MCP server runs as a child process of a session. Its working directory defaults to the project root and can be narrowed to a subdirectory; absolute paths must stay inside the project or its extra roots.",
          "Environment variables can be set explicitly or passed through from the host by name. Values are stored with the agent and never written to logs.",
          "The process starts on the session's first run and is reused for later turns. It stops when the session is deleted or closed, after an idle timeout, or when the server shuts down.",
        ],
      },
    ],
    related: ["agent.tools"],
  },
```

- [ ] **Step 2: Update the roadmap**

Change line 18 to:

```markdown
| MCP for external tools/resources | DONE | Remote URL + stdio agent bindings; session-scoped stdio processes with cwd/env sandboxing, MCP Apps relay, create/edit UI. |
```

Add to the spec coverage table:

```markdown
| 37 | D22 stdio MCP servers (session lifecycle + create/edit UI) | `specs/2026-11-22-stdio-mcp-servers-design.md` | `plans/2026-11-22-stdio-mcp-servers.md` |
```

- [ ] **Step 3: Run all checks**

```powershell
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-providers -q
uv run pytest packages/agentbox-api -q
uv run ruff check --fix packages
uv run ty check packages
```

```powershell
cd apps/web
bun run test
bun run build
```

Expected: all commands pass. The `uvx mcp-server-time` test may SKIP when `uvx` is unavailable; any other failure must be fixed before committing.

- [ ] **Step 4: Commit**

```powershell
git add apps/web/src/help/content.ts docs/ROADMAP.md
git commit -m "docs: document stdio MCP servers and mark D22 complete"
```
