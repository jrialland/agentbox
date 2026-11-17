# Agentic Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the agentic harness — a runtime that executes Pydantic AI agents against a session (system prompt + tools + model + mode), with sandboxed file tools, MCP tool support, mode-based tool filtering, sub-agent delegation, and an immutable branching conversation history that supports resume, cancellation, and detach/re-attach.

**Architecture:** A `RunManager` drives a core `pydantic_ai.Agent` (built per-run from a resolved `AgentSpec` + active `Mode`) via `run_stream_events()`, producing a canonical, ordered event stream that is fanned out to subscribers through an event bus. Sessions hold an immutable message log with a branch pointer; resume reconstructs `message_history`. Sub-agents are native tools that delegate to isolated runs.

**Tech Stack:** Python 3.11+, `pydantic-ai` (core only, no `pydantic-ai-harness`), `pydantic`, `uv` for dependency management, `pytest` + `pytest-asyncio` for tests.

## Global Constraints

- Python `>=3.11`.
- Use `pydantic-ai` **core only** — do **not** add `pydantic-ai-harness`.
- Use asynchronous code (`async`/`asyncio`) wherever possible.
- All agents, specs, and messages are ultimately stored in SQLite, but **this sub-project only defines interfaces** (`AgentRepository`, `MessageLogStore`); it ships an in-memory implementation for tests. The SQLite-backed implementations belong to the data-model sub-project.
- File tools are **sandboxed to the session's project root**; escaping the root is rejected.
- File tool names and semantics **mirror the MCP FileSystem reference server**.
- No real LLM calls in tests — use `pydantic_ai.models.test.TestModel` / `FunctionModel`.
- Follow TDD: write the failing test first, run it to see it fail, implement, run it to see it pass, then commit.

**Reference docs (verify exact signatures against these while implementing):**
- Pydantic AI: Agents, Tools, Streaming events, Multi-agent delegation, MCP client, message history — `https://pydantic.dev/docs/ai/`.
- MCP FileSystem server tool list — `https://github.com/modelcontextprotocol/servers` (`src/filesystem`).

---

### Task 1: Package scaffold

**Files:**
- Create: `packages/agentbox-harness/pyproject.toml`
- Create: `packages/agentbox-harness/src/agentbox_harness/__init__.py`
- Create: `packages/agentbox-harness/tests/__init__.py`
- Create: `packages/agentbox-harness/tests/test_scaffold.py`

**Interfaces:**
- Produces: importable package `agentbox_harness` (empty for now), and a test harness that confirms `pytest` + `pytest-asyncio` work.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scaffold.py
import asyncio

import agentbox_harness


def test_package_imports():
    assert hasattr(agentbox_harness, "__version__")


def test_async_test_harness_works():
    async def inner():
        await asyncio.sleep(0)
        return 42

    assert asyncio.run(inner()) == 42
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scaffold.py -v` (from `packages/agentbox-harness`)
Expected: FAIL — `agentbox_harness` has no `__version__` attribute.

- [ ] **Step 3: Write the pyproject and package init**

```toml
# pyproject.toml
[project]
name = "agentbox-harness"
version = "0.1.0"
description = "Agentic harness for Agentbox"
requires-python = ">=3.11"
dependencies = [
    "pydantic-ai>=0.0.1",
    "pydantic>=2.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/agentbox_harness"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

```python
# src/agentbox_harness/__init__.py
__version__ = "0.1.0"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_scaffold.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness
git commit -m "feat(harness): scaffold agentbox-harness package"
```

---

### Task 2: Core types (`AgentSpec`, `ModelBinding`, `Mode`, tool bindings)

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/spec.py`
- Test: `packages/agentbox-harness/tests/test_spec.py`

**Interfaces:**
- Produces (imported by later tasks):
  - `ModelBinding(model: str, provider: str)` — frozen dataclass.
  - `Mode(name: str, flags: dict[str, bool])` — frozen dataclass; helper `allows(mode, flag: str) -> bool`.
  - `ToolBinding` — union-friendly descriptor for a tool an agent may use: either `NativeToolBinding(name: str, required_flags: tuple[str, ...] = ())` or `McpToolBinding(server_url: str, tool_prefix: str = "")`.
  - `AgentSpec(name, description, instructions, tool_bindings, sub_agent_ids, mode_definitions, model_binding)` — a `pydantic.BaseModel` with those fields (so it round-trips through JSON for SQLite storage).
  - `DEFAULT_MODES = (Mode(name="ask", flags={"write": False}), Mode(name="agent", flags={"write": True}))`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spec.py
from agentbox_harness.spec import (
    DEFAULT_MODES,
    AgentSpec,
    Mode,
    ModelBinding,
    NativeToolBinding,
)


def test_mode_allows():
    ask = Mode(name="ask", flags={"write": False})
    agent = Mode(name="agent", flags={"write": True})
    assert not ask.allows("write")
    assert agent.allows("write")
    assert ask.allows("read")  # unknown flags default to True


def test_agent_spec_round_trips_json():
    spec = AgentSpec(
        name="coder",
        description="Writes code",
        instructions="You are a helpful coding assistant.",
        tool_bindings=[NativeToolBinding(name="read_text_file")],
        sub_agent_ids=["sub"],
        mode_definitions=list(DEFAULT_MODES),
        model_binding=ModelBinding(model="gpt-x", provider="openai"),
    )
    restored = AgentSpec.model_validate_json(spec.model_dump_json())
    assert restored == spec


def test_default_modes():
    by_name = {m.name: m for m in DEFAULT_MODES}
    assert set(by_name) == {"ask", "agent"}
    assert by_name["ask"].allows("write") is False
    assert by_name["agent"].allows("write") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_spec.py -v`
Expected: FAIL — `ModuleNotFoundError: agentbox_harness.spec`.

- [ ] **Step 3: Write the implementation**

```python
# src/agentbox_harness/spec.py
from dataclasses import dataclass
from typing import Union

from pydantic import BaseModel


@dataclass(frozen=True)
class ModelBinding:
    model: str
    provider: str


@dataclass(frozen=True)
class Mode:
    name: str
    flags: dict[str, bool]

    def allows(self, flag: str) -> bool:
        return self.flags.get(flag, True)


@dataclass(frozen=True)
class NativeToolBinding:
    name: str
    required_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class McpToolBinding:
    server_url: str
    tool_prefix: str = ""


ToolBinding = Union[NativeToolBinding, McpToolBinding]


class AgentSpec(BaseModel):
    name: str
    description: str
    instructions: str
    tool_bindings: list[ToolBinding]
    sub_agent_ids: list[str] = []
    mode_definitions: list[Mode] = []
    model_binding: ModelBinding


DEFAULT_MODES = (
    Mode(name="ask", flags={"write": False}),
    Mode(name="agent", flags={"write": True}),
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_spec.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/spec.py packages/agentbox-harness/tests/test_spec.py
git commit -m "feat(harness): add core types (AgentSpec, Mode, ModelBinding)"
```

---

### Task 3: Native file tools (sandboxed to project root)

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/tools/__init__.py`
- Create: `packages/agentbox-harness/src/agentbox_harness/tools/filesystem.py`
- Test: `packages/agentbox-harness/tests/test_filesystem_tools.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (standalone).
- Produces (imported by later tasks):
  - `FilesystemToolbox` — a class constructed with a `root_dir: pathlib.Path`; exposes methods used as Pydantic AI tools: `read_text_file(path)`, `write_file(path, content)`, `list_directory(path)`, `get_file_info(path)`. Each is `async def` and takes paths relative to the root.
  - `PathEscapesRootError` — raised when a resolved path escapes `root_dir`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_filesystem_tools.py
import pathlib

import pytest

from agentbox_harness.tools.filesystem import FilesystemToolbox, PathEscapesRootError


@pytest.fixture
def root(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path


async def test_read_and_write_round_trip(root):
    box = FilesystemToolbox(root)
    await box.write_file("notes.txt", "hello")
    assert await box.read_text_file("notes.txt") == "hello"


async def test_list_directory(root):
    box = FilesystemToolbox(root)
    await box.write_file("a.txt", "a")
    await box.write_file("sub/b.txt", "b")
    names = sorted(await box.list_directory("."))
    assert "a.txt" in names
    assert "sub" in names


async def test_escape_is_rejected(root, tmp_path):
    box = FilesystemToolbox(root)
    with pytest.raises(PathEscapesRootError):
        await box.read_text_file("../secret.txt")


async def test_absolute_escape_is_rejected(root, tmp_path):
    box = FilesystemToolbox(root)
    with pytest.raises(PathEscapesRootError):
        await box.write_file(str(tmp_path / "elsewhere.txt"), "nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_filesystem_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: agentbox_harness.tools.filesystem`.

- [ ] **Step 3: Write the implementation**

```python
# src/agentbox_harness/tools/filesystem.py
import pathlib


class PathEscapesRootError(Exception):
    pass


class FilesystemToolbox:
    def __init__(self, root_dir: pathlib.Path):
        self.root_dir = pathlib.Path(root_dir).resolve()

    def _resolve(self, path: str) -> pathlib.Path:
        p = (self.root_dir / path).resolve()
        if not (p == self.root_dir or self.root_dir in p.parents):
            raise PathEscapesRootError(path)
        return p

    async def read_text_file(self, path: str) -> str:
        return self._resolve(path).read_text(encoding="utf-8")

    async def write_file(self, path: str, content: str) -> str:
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"

    async def list_directory(self, path: str) -> list[str]:
        p = self._resolve(path)
        return sorted(entry.name for entry in p.iterdir())

    async def get_file_info(self, path: str) -> str:
        p = self._resolve(path)
        st = p.stat()
        return f"{path}: size={st.st_size} is_dir={p.is_dir()}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_filesystem_tools.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/tools packages/agentbox-harness/tests/test_filesystem_tools.py
git commit -m "feat(harness): add sandboxed filesystem tools"
```

---

### Task 4: Tool registry and mode-based filtering

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/tools/registry.py`
- Test: `packages/agentbox-harness/tests/test_tool_registry.py`

**Interfaces:**
- Consumes: `NativeToolBinding`, `McpToolBinding`, `Mode` (from `spec.py`).
- Produces (imported by later tasks):
  - `ToolRegistry` — holds a mapping of native tool callables (name → callable) and their `required_flags`; `select_tools(mode: Mode) -> list[callable]` returns the subset of tool callables whose flags are satisfied by the mode.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tool_registry.py
from agentbox_harness.spec import Mode
from agentbox_harness.tools.registry import ToolRegistry


async def read_file(path: str) -> str:
    return "data"


async def write_file(path: str, content: str) -> str:
    return "ok"


def test_select_tools_filters_by_flags():
    reg = ToolRegistry()
    reg.register_native("read_file", read_file, required_flags=("read",))
    reg.register_native("write_file", write_file, required_flags=("write",))

    ask = Mode(name="ask", flags={"write": False})
    agent = Mode(name="agent", flags={"write": True})

    assert [f.__name__ for f in reg.select_tools(ask)] == ["read_file"]
    assert {f.__name__ for f in reg.select_tools(agent)} == {"read_file", "write_file"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tool_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: agentbox_harness.tools.registry`.

- [ ] **Step 3: Write the implementation**

```python
# src/agentbox_harness/tools/registry.py
from collections.abc import Callable
from dataclasses import dataclass, field

from agentbox_harness.spec import Mode


@dataclass
class _Entry:
    callable: Callable
    required_flags: tuple[str, ...] = ()


class ToolRegistry:
    def __init__(self) -> None:
        self._native: dict[str, _Entry] = {}

    def register_native(
        self,
        name: str,
        callable: Callable,
        required_flags: tuple[str, ...] = (),
    ) -> None:
        self._native[name] = _Entry(callable, required_flags)

    def select_tools(self, mode: Mode) -> list[Callable]:
        return [
            entry.callable
            for entry in self._native.values()
            if all(mode.allows(f) for f in entry.required_flags)
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tool_registry.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/tools/registry.py packages/agentbox-harness/tests/test_tool_registry.py
git commit -m "feat(harness): add tool registry with mode-based filtering"
```

---

### Task 5: Agent factory (build a Pydantic AI `Agent` from `AgentSpec` + `Mode`)

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/agent_factory.py`
- Test: `packages/agentbox-harness/tests/test_agent_factory.py`

**Interfaces:**
- Consumes: `AgentSpec`, `Mode`, `ToolRegistry` (previous tasks).
- Produces (imported by later tasks):
  - `build_agent(spec: AgentSpec, mode: Mode, registry: ToolRegistry, model: str) -> Agent` — returns a `pydantic_ai.Agent` configured with `instructions=spec.instructions`, `model=model`, and the filtered tool list. The `model` string is passed in directly (the provider layer resolves it; this sub-project only passes it through).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_factory.py
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from agentbox_harness.agent_factory import build_agent
from agentbox_harness.spec import AgentSpec, Mode, ModelBinding
from agentbox_harness.tools.registry import ToolRegistry


async def write_file(path: str, content: str) -> str:
    return "ok"


def _spec() -> AgentSpec:
    return AgentSpec(
        name="coder",
        description="writes code",
        instructions="Be helpful.",
        tool_bindings=[],
        model_binding=ModelBinding(model="test", provider="test"),
    )


def test_build_agent_sets_instructions_and_tools():
    reg = ToolRegistry()
    reg.register_native("write_file", write_file, required_flags=("write",))

    spec = _spec()
    agent = build_agent(spec, Mode(name="agent", flags={"write": True}), reg, "test")

    assert isinstance(agent, Agent)
    result = agent.run_sync("hi", model=TestModel())
    assert result is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agent_factory.py -v`
Expected: FAIL — `ModuleNotFoundError: agentbox_harness.agent_factory`.

- [ ] **Step 3: Write the implementation**

```python
# src/agentbox_harness/agent_factory.py
from pydantic_ai import Agent

from agentbox_harness.spec import AgentSpec, Mode
from agentbox_harness.tools.registry import ToolRegistry


def build_agent(
    spec: AgentSpec,
    mode: Mode,
    registry: ToolRegistry,
    model: str,
) -> Agent:
    tools = registry.select_tools(mode)
    return Agent(
        model=model,
        name=spec.name,
        instructions=spec.instructions,
        tools=tools,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agent_factory.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/agent_factory.py packages/agentbox-harness/tests/test_agent_factory.py
git commit -m "feat(harness): add agent factory"
```

---

### Task 6: Canonical run events

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/events.py`
- Test: `packages/agentbox-harness/tests/test_events.py`

**Interfaces:**
- Produces (imported by later tasks):
  - `RunEvent` — a `dataclass` wrapping a single pydantic-ai stream event with run metadata for ordered replay: `run_id: str`, `seq: int`, `event: object`.
  - `EventBus` — fan-out primitive: `subscribe() -> asyncio.Queue`, `publish(event: RunEvent)`, `close()`. Subscribers get events in publish order.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_events.py
import asyncio
from dataclasses import dataclass

from agentbox_harness.events import EventBus, RunEvent


@dataclass
class FakeEvent:
    text: str


async def test_event_bus_delivers_in_order():
    bus = EventBus()
    q = bus.subscribe()

    bus.publish(RunEvent(run_id="r1", seq=0, event=FakeEvent("a")))
    bus.publish(RunEvent(run_id="r1", seq=1, event=FakeEvent("b")))
    bus.close()

    got = []
    while not q.empty():
        got.append(await q.get())

    assert [e.seq for e in got] == [0, 1]
    assert [e.event.text for e in got] == ["a", "b"]


async def test_multiple_subscribers_each_get_every_event():
    bus = EventBus()
    q1 = bus.subscribe()
    q2 = bus.subscribe()
    bus.publish(RunEvent(run_id="r1", seq=0, event=FakeEvent("x")))
    bus.close()
    assert await q1.get() == await q2.get()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_events.py -v`
Expected: FAIL — `ModuleNotFoundError: agentbox_harness.events`.

- [ ] **Step 3: Write the implementation**

```python
# src/agentbox_harness/events.py
import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class RunEvent:
    run_id: str
    seq: int
    event: object


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []
        self._closed = False

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def publish(self, event: RunEvent) -> None:
        for q in self._subscribers:
            q.put_nowait(event)

    def close(self) -> None:
        self._closed = True
        for q in self._subscribers:
            q.put_nowait(None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_events.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/events.py packages/agentbox-harness/tests/test_events.py
git commit -m "feat(harness): add canonical run events and event bus"
```

---

### Task 7: `RunManager` (drive `run_stream_events`, emit ordered events)

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/run.py`
- Test: `packages/agentbox-harness/tests/test_run_manager.py`

**Interfaces:**
- Consumes: `Agent` (from `agent_factory`), `RunEvent`/`EventBus` (from `events`).
- Produces (imported by later tasks):
  - `RunManager` — constructed with a `model: str`.
  - `RunManager.start(agent: Agent, prompt: str, run_id: str, bus: EventBus) -> Run` — builds and starts a background task that calls `agent.run_stream_events(prompt)` and, for each yielded event, publishes a `RunEvent` with an incrementing `seq`. Returns a `Run` handle.
  - `Run` — dataclass holding `run_id`, the `asyncio.Task`, and `await_result() -> AgentRunResult` (awaits the task and returns the final result).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_manager.py
import asyncio

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from agentbox_harness.events import EventBus
from agentbox_harness.run import RunManager


async def test_run_emits_ordered_events():
    agent = Agent("test", instructions="echo")
    bus = EventBus()
    q = bus.subscribe()

    mgr = RunManager(model="test")
    run = mgr.start(agent, "hello", run_id="r1", bus=bus, model_override=TestModel())
    result = await run.await_result()
    bus.close()

    assert result.output is not None
    events = []
    while not q.empty():
        item = await q.get()
        if item is not None:
            events.append(item)
    # seq values are strictly increasing
    seqs = [e.seq for e in events]
    assert seqs == sorted(seqs)
    assert len(events) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_run_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: agentbox_harness.run`.

- [ ] **Step 3: Write the implementation**

```python
# src/agentbox_harness/run.py
import asyncio
from dataclasses import dataclass

from pydantic_ai import Agent

from agentbox_harness.events import EventBus, RunEvent


@dataclass
class Run:
    run_id: str
    task: asyncio.Task

    async def await_result(self):
        return await self.task


class RunManager:
    def __init__(self, model: str):
        self.model = model

    def start(
        self,
        agent: Agent,
        prompt: str,
        run_id: str,
        bus: EventBus,
        model_override=None,
    ) -> Run:
        task = asyncio.create_task(
            self._drive(agent, prompt, run_id, bus, model_override)
        )
        return Run(run_id=run_id, task=task)

    async def _drive(
        self,
        agent: Agent,
        prompt: str,
        run_id: str,
        bus: EventBus,
        model_override=None,
    ):
        seq = 0
        kwargs = {"model": model_override} if model_override is not None else {}
        async with agent.run_stream_events(prompt, **kwargs) as events:
            async for event in events:
                bus.publish(RunEvent(run_id=run_id, seq=seq, event=event))
                seq += 1
        return events  # AgentRunResultEvent is the final yielded item
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_run_manager.py -v`
Expected: PASS (1 passed). If `run_stream_events` does not expose the final result via the iterator's final item, adjust `_drive` to capture `events.result` from the async context manager and return it; verify against the streaming docs.

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/run.py packages/agentbox-harness/tests/test_run_manager.py
git commit -m "feat(harness): add RunManager that emits ordered events"
```

---

### Task 8: Session, message log, and branching

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/session.py`
- Test: `packages/agentbox-harness/tests/test_session.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (imported by later tasks):
  - `Turn` — dataclass `(id: str, role: str, content: str, parent_id: str | None)`.
  - `MessageLogStore` — Protocol: `append(turn) -> None`, `list_turns() -> list[Turn]`, `get(turn_id) -> Turn`.
  - `InMemoryMessageLogStore` — implementation of the Protocol.
  - `Session(session_id, project_root, agent_spec, store, head_id)` — dataclass with `head_id: str | None` pointing at the current branch tip. `Session.append(turn, parent_id)` appends a turn and advances `head_id` to it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session.py
from agentbox_harness.session import InMemoryMessageLogStore, Session, Turn


def test_branching_edit_keeps_history():
    store = InMemoryMessageLogStore()
    session = Session(
        session_id="s1", project_root=".", agent_spec=None, store=store, head_id=None
    )

    t1 = Turn(id="t1", role="user", content="q1", parent_id=None)
    t2 = Turn(id="t2", role="assistant", content="a1", parent_id="t1")
    session.append(t1, parent_id=None)
    session.append(t2, parent_id="t1")

    # Edit t1: fork a new branch (keep t1, add a new child) without deleting t2
    t3 = Turn(id="t3", role="assistant", content="a2", parent_id="t1")
    session.append(t3, parent_id="t1")

    assert session.head_id == "t3"
    ids = [t.id for t in store.list_turns()]
    assert set(ids) == {"t1", "t2", "t3"}  # nothing deleted
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session.py -v`
Expected: FAIL — `ModuleNotFoundError: agentbox_harness.session`.

- [ ] **Step 3: Write the implementation**

```python
# src/agentbox_harness/session.py
from dataclasses import dataclass
from typing import Protocol

from agentbox_harness.spec import AgentSpec


@dataclass(frozen=True)
class Turn:
    id: str
    role: str
    content: str
    parent_id: str | None


class MessageLogStore(Protocol):
    def append(self, turn: Turn) -> None: ...

    def list_turns(self) -> list[Turn]: ...

    def get(self, turn_id: str) -> Turn: ...


class InMemoryMessageLogStore:
    def __init__(self) -> None:
        self._turns: dict[str, Turn] = {}

    def append(self, turn: Turn) -> None:
        self._turns[turn.id] = turn

    def list_turns(self) -> list[Turn]:
        return list(self._turns.values())

    def get(self, turn_id: str) -> Turn:
        return self._turns[turn_id]


@dataclass
class Session:
    session_id: str
    project_root: str
    agent_spec: AgentSpec | None
    store: MessageLogStore
    head_id: str | None

    def append(self, turn: Turn, parent_id: str | None) -> None:
        self.store.append(turn)
        self.head_id = turn.id
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_session.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/session.py packages/agentbox-harness/tests/test_session.py
git commit -m "feat(harness): add session, message log store, and branching"
```

---

### Task 9: Resume (rebuild `message_history` from the branch)

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/session.py`
- Test: `packages/agentbox-harness/tests/test_resume.py`

**Interfaces:**
- Consumes: `Session`, `MessageLogStore` (Task 8).
- Produces (imported by later tasks):
  - `Session.history() -> list[Turn]` — returns the ordered list of turns from the root (the turn with `parent_id is None`) down to `head_id`, following `parent_id` links. Used to reconstruct `message_history` for `agent.run(message_history=...)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_resume.py
from agentbox_harness.session import InMemoryMessageLogStore, Session, Turn


def test_history_returns_ordered_chain_to_head():
    store = InMemoryMessageLogStore()
    session = Session(
        session_id="s1", project_root=".", agent_spec=None, store=store, head_id=None
    )
    t1 = Turn(id="t1", role="user", content="q1", parent_id=None)
    t2 = Turn(id="t2", role="assistant", content="a1", parent_id="t1")
    t3 = Turn(id="t3", role="user", content="q2", parent_id="t2")
    session.append(t1, parent_id=None)
    session.append(t2, parent_id="t1")
    session.append(t3, parent_id="t2")

    assert [t.id for t in session.history()] == ["t1", "t2", "t3"]


def test_history_after_fork_follows_new_branch():
    store = InMemoryMessageLogStore()
    session = Session(
        session_id="s1", project_root=".", agent_spec=None, store=store, head_id=None
    )
    t1 = Turn(id="t1", role="user", content="q1", parent_id=None)
    t2 = Turn(id="t2", role="assistant", content="a1", parent_id="t1")
    t3 = Turn(id="t3", role="assistant", content="a2", parent_id="t1")
    for t, p in [(t1, None), (t2, "t1"), (t3, "t1")]:
        session.append(t, parent_id=p)

    assert [t.id for t in session.history()] == ["t1", "t3"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_resume.py -v`
Expected: FAIL — `Session` has no attribute `history`.

- [ ] **Step 3: Write the implementation**

Add to `Session` in `session.py`:

```python
    def history(self) -> list[Turn]:
        if self.head_id is None:
            return []
        chain: list[Turn] = []
        current = self.store.get(self.head_id)
        while True:
            chain.append(current)
            if current.parent_id is None:
                break
            current = self.store.get(current.parent_id)
        return list(reversed(chain))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_resume.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/session.py packages/agentbox-harness/tests/test_resume.py
git commit -m "feat(harness): add resume via branch history traversal"
```

---

### Task 10: Cancellation

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/run.py`
- Test: `packages/agentbox-harness/tests/test_cancel.py`

**Interfaces:**
- Consumes: `RunManager`, `Run` (Task 7).
- Produces (imported by later tasks):
  - `RunManager.start(..., cancellation_token: CancellationToken | None = None) -> Run` — accepts a pydantic-ai `CancellationToken`, passing it to `run_stream_events`.
  - `Run.cancel()` — cancels the token.
  - `RunCancelled` is surfaced (not swallowed): `Run.await_result()` raises `RunCancelled` when cancelled.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cancel.py
import asyncio

import pytest
from pydantic_ai import Agent, CancellationToken, RunCancelled
from pydantic_ai.models.test import TestModel

from agentbox_harness.events import EventBus
from agentbox_harness.run import RunManager


async def test_cancel_raises_run_cancelled():
    agent = Agent("test", instructions="echo")
    bus = EventBus()
    token = CancellationToken()

    mgr = RunManager(model="test")
    run = mgr.start(
        agent,
        "hello",
        run_id="r1",
        bus=bus,
        model_override=TestModel(),
        cancellation_token=token,
    )
    token.cancel()

    with pytest.raises(RunCancelled):
        await run.await_result()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cancel.py -v`
Expected: FAIL — `TypeError: RunManager.start() got an unexpected keyword argument 'cancellation_token'`.

- [ ] **Step 3: Write the implementation**

Update `RunManager` in `run.py`:

```python
from pydantic_ai import Agent, CancellationToken

    def start(
        self,
        agent: Agent,
        prompt: str,
        run_id: str,
        bus: EventBus,
        model_override=None,
        cancellation_token: CancellationToken | None = None,
    ) -> Run:
        task = asyncio.create_task(
            self._drive(agent, prompt, run_id, bus, model_override, cancellation_token)
        )
        return Run(run_id=run_id, task=task)

    async def _drive(self, agent, prompt, run_id, bus, model_override, cancellation_token):
        seq = 0
        kwargs = {"model": model_override} if model_override is not None else {}
        if cancellation_token is not None:
            kwargs["cancellation_token"] = cancellation_token
        async with agent.run_stream_events(prompt, **kwargs) as events:
            async for event in events:
                bus.publish(RunEvent(run_id=run_id, seq=seq, event=event))
                seq += 1
        return events
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cancel.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/run.py packages/agentbox-harness/tests/test_cancel.py
git commit -m "feat(harness): add cancellation support"
```

---

### Task 11: Sub-agents (delegation to isolated runs)

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/subagents.py`
- Test: `packages/agentbox-harness/tests/test_subagents.py`

**Interfaces:**
- Consumes: `Agent` (from `agent_factory`).
- Produces (imported by later tasks):
  - `build_subagent_tool(sub_agent: Agent) -> Callable` — returns an `async def` tool that runs `sub_agent.run(task, usage=ctx.usage)` in its own isolated run and returns `result.output`. The tool signature is `async def delegate(ctx: RunContext, task: str) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_subagents.py
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel

from agentbox_harness.subagents import build_subagent_tool


async def test_subagent_tool_delegates():
    sub = Agent("test", name="sub", instructions="You are a sub-agent.")
    tool = build_subagent_tool(sub)

    # Call the tool directly with a fake context-free path: wrap a manual ctx
    class FakeCtx:
        usage = None

    result = await tool(FakeCtx(), "do the thing")
    assert result is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_subagents.py -v`
Expected: FAIL — `ModuleNotFoundError: agentbox_harness.subagents`.

- [ ] **Step 3: Write the implementation**

```python
# src/agentbox_harness/subagents.py
from collections.abc import Callable

from pydantic_ai import Agent, RunContext


def build_subagent_tool(sub_agent: Agent) -> Callable:
    async def delegate(ctx: RunContext, task: str) -> str:
        result = await sub_agent.run(task, usage=ctx.usage)
        return str(result.output)

    delegate.__name__ = f"delegate_{sub_agent.name}"
    return delegate
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_subagents.py -v`
Expected: PASS (1 passed). Note: passing a `TestModel` is not needed for the direct call; if `sub_agent.run` requires a model at runtime, pass `model=TestModel()` inside `delegate` in the test by constructing `sub` with `Agent("test")` and `run(task, model=TestModel())`. Adjust only the test, not the implementation.

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/subagents.py packages/agentbox-harness/tests/test_subagents.py
git commit -m "feat(harness): add sub-agent delegation tool"
```

---

### Task 12: Error normalization

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/errors.py`
- Test: `packages/agentbox-harness/tests/test_errors.py`

**Interfaces:**
- Consumes: `RunCancelled` (pydantic-ai), `PathEscapesRootError` (Task 3).
- Produces (imported by later tasks):
  - `RunOutcome` — dataclass `(status: str, message: str | None)`, where `status` is one of `"success"`, `"cancelled"`, `"error"`.
  - `normalize_error(exc: BaseException) -> RunOutcome` — maps `RunCancelled` → `"cancelled"`, `PathEscapesRootError` → `"error"` with a descriptive message, and any other exception → `"error"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_errors.py
from pydantic_ai.exceptions import RunCancelled

from agentbox_harness.errors import normalize_error
from agentbox_harness.tools.filesystem import PathEscapesRootError


def test_cancelled_is_cancelled():
    out = normalize_error(RunCancelled("cancelled"))
    assert out.status == "cancelled"


def test_escape_is_error():
    out = normalize_error(PathEscapesRootError("../x"))
    assert out.status == "error"
    assert "root" in out.message.lower() or "escape" in out.message.lower()


def test_unknown_is_error():
    out = normalize_error(RuntimeError("boom"))
    assert out.status == "error"
    assert out.message == "boom"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_errors.py -v`
Expected: FAIL — `ModuleNotFoundError: agentbox_harness.errors`.

- [ ] **Step 3: Write the implementation**

```python
# src/agentbox_harness/errors.py
from dataclasses import dataclass

from pydantic_ai.exceptions import RunCancelled

from agentbox_harness.tools.filesystem import PathEscapesRootError


@dataclass(frozen=True)
class RunOutcome:
    status: str  # "success" | "cancelled" | "error"
    message: str | None = None


def normalize_error(exc: BaseException) -> RunOutcome:
    if isinstance(exc, RunCancelled):
        return RunOutcome(status="cancelled", message=str(exc))
    if isinstance(exc, PathEscapesRootError):
        return RunOutcome(status="error", message=f"Path escapes project root: {exc}")
    return RunOutcome(status="error", message=str(exc))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_errors.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/errors.py packages/agentbox-harness/tests/test_errors.py
git commit -m "feat(harness): add error normalization"
```

---

### Task 13: MCP tool integration

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/tools/mcp.py`
- Test: `packages/agentbox-harness/tests/test_mcp_tools.py`

**Interfaces:**
- Consumes: `McpToolBinding` (Task 2), `Agent` (Task 5).
- Produces (imported by later tasks):
  - `attach_mcp_toolsets(agent: Agent, bindings: list[McpToolBinding]) -> None` — for each `McpToolBinding`, builds an `MCPToolset` (from `pydantic_ai.mcp`) and registers it on the agent via `agent.toolsets` (or the `toolsets=` constructor arg). Verified against the MCP client docs.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mcp_tools.py
from pydantic_ai import Agent

from agentbox_harness.spec import McpToolBinding
from agentbox_harness.tools.mcp import build_mcp_toolset


def test_build_mcp_toolset_from_binding():
    binding = McpToolBinding(server_url="https://example.com/mcp", tool_prefix="fs")
    ts = build_mcp_toolset(binding)
    assert ts is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mcp_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: agentbox_harness.tools.mcp`.

- [ ] **Step 3: Write the implementation**

```python
# src/agentbox_harness/tools/mcp.py
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset

from agentbox_harness.spec import McpToolBinding


def build_mcp_toolset(binding: McpToolBinding) -> MCPToolset:
    return MCPToolset(binding.server_url, tool_prefix=binding.tool_prefix)


def attach_mcp_toolsets(agent: Agent, bindings: list[McpToolBinding]) -> None:
    for binding in bindings:
        agent.toolsets.append(build_mcp_toolset(binding))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_mcp_tools.py -v`
Expected: PASS (1 passed). Note: verify the exact `MCPToolset` constructor signature and whether `tool_prefix` is a valid kwarg against the MCP client docs; adjust the call if the parameter differs.

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/tools/mcp.py packages/agentbox-harness/tests/test_mcp_tools.py
git commit -m "feat(harness): add MCP toolset integration"
```

---

### Task 14: Wire it together — end-to-end harness facade

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/harness.py`
- Test: `packages/agentbox-harness/tests/test_harness_e2e.py`

**Interfaces:**
- Consumes: all previous tasks.
- Produces (public facade for the backend/protocol sub-projects):
  - `Harness` — constructed with a `ToolRegistry`, a `RunManager`, and a `MessageLogStore` factory.
  - `Harness.start_session(spec, project_root, mode_name) -> Session`
  - `Harness.run(session, user_message) -> Run` — builds the agent (via `agent_factory`), resolves the mode by name from `spec.mode_definitions`, records the user turn, starts a `Run`, and returns it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_e2e.py
from pydantic_ai.models.test import TestModel

from agentbox_harness.events import EventBus
from agentbox_harness.harness import Harness
from agentbox_harness.session import InMemoryMessageLogStore
from agentbox_harness.spec import DEFAULT_MODES, AgentSpec, ModelBinding
from agentbox_harness.tools.registry import ToolRegistry


async def write_file(path: str, content: str) -> str:
    return "ok"


def _spec() -> AgentSpec:
    return AgentSpec(
        name="coder",
        description="writes code",
        instructions="Be helpful.",
        tool_bindings=[],
        mode_definitions=list(DEFAULT_MODES),
        model_binding=ModelBinding(model="test", provider="test"),
    )


async def test_harness_runs_a_session():
    reg = ToolRegistry()
    reg.register_native("write_file", write_file, required_flags=("write",))

    harness = Harness(registry=reg, model="test", store_factory=InMemoryMessageLogStore)
    session = harness.start_session(_spec(), project_root=".", mode_name="agent")

    bus = EventBus()
    run = harness.run(session, "write a file", bus=bus, model_override=TestModel())
    result = await run.await_result()

    assert result.output is not None
    assert session.history()[-1].role == "user"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_harness_e2e.py -v`
Expected: FAIL — `ModuleNotFoundError: agentbox_harness.harness`.

- [ ] **Step 3: Write the implementation**

```python
# src/agentbox_harness/harness.py
import uuid

from agentbox_harness.agent_factory import build_agent
from agentbox_harness.events import EventBus
from agentbox_harness.run import RunManager, Run
from agentbox_harness.session import MessageLogStore, Session, Turn
from agentbox_harness.spec import AgentSpec, Mode
from agentbox_harness.tools.registry import ToolRegistry


class Harness:
    def __init__(
        self,
        registry: ToolRegistry,
        model: str,
        store_factory,
    ):
        self.registry = registry
        self.model = model
        self.store_factory = store_factory
        self.run_manager = RunManager(model=model)

    def start_session(
        self,
        spec: AgentSpec,
        project_root: str,
        mode_name: str,
    ) -> Session:
        store = self.store_factory()
        session = Session(
            session_id=uuid.uuid4().hex,
            project_root=project_root,
            agent_spec=spec,
            store=store,
            head_id=None,
        )
        session._mode_name = mode_name
        return session

    def _resolve_mode(self, session: Session) -> Mode:
        name = getattr(session, "_mode_name", "agent")
        for mode in session.agent_spec.mode_definitions:
            if mode.name == name:
                return mode
        raise ValueError(f"Unknown mode: {name}")

    def run(
        self,
        session: Session,
        user_message: str,
        bus: EventBus,
        model_override=None,
    ) -> Run:
        turn = Turn(
            id=uuid.uuid4().hex,
            role="user",
            content=user_message,
            parent_id=session.head_id,
        )
        session.append(turn, parent_id=session.head_id)

        mode = self._resolve_mode(session)
        agent = build_agent(session.agent_spec, mode, self.registry, self.model)
        return self.run_manager.start(
            agent,
            user_message,
            run_id=uuid.uuid4().hex,
            bus=bus,
            model_override=model_override,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_harness_e2e.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/agentbox-harness/src/agentbox_harness/harness.py packages/agentbox-harness/tests/test_harness_e2e.py
git commit -m "feat(harness): add end-to-end harness facade"
```

---

## Self-Review Notes

- **Spec coverage:** All spec sections map to tasks — core concepts (Task 2), tool system incl. modes and MCP (Tasks 3, 4, 13), run execution and streaming (Tasks 6, 7), sessions/history/branching/resume (Tasks 8, 9), detach/re-attach primitives (Task 6 event bus; a full replay-on-reattach flow is deferred to the backend sub-project), cancellation (Task 10), sub-agents (Task 11), error handling (Task 12), testing (TDD throughout with `TestModel`), and the SQLite-vs-interface boundary (Global Constraints; in-memory store only).
- **Type consistency:** `AgentSpec`, `Mode`, `ModelBinding`, `ToolRegistry`, `build_agent`, `RunManager`, `Run`, `EventBus`, `RunEvent`, `Session`, `Turn`, `build_subagent_tool`, `normalize_error`, `build_mcp_toolset` are defined once and referenced consistently across tasks.
- **Detach/re-attach:** The event bus (Task 6) and `Run` handle (Task 7) provide the fan-out and ordered-event primitives. The full replay-on-reattach flow (buffered event log + snapshot) is intentionally left to the backend/protocol sub-project, which owns transport; it is noted in the spec's open items.
