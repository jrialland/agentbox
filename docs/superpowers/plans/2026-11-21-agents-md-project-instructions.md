# D20 AGENTS.md Project Instructions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load global, project-root, and dynamically discovered nested AGENTS.md guidance into agent prompts with bounded size, correct precedence, refresh semantics, and subagent inheritance.

**Architecture:** Add a project-instructions module that reads global/root files for the system prompt and a session-scoped tool hook that discovers nested AGENTS.md files as the agent touches paths. Keep a process-local session ledger for delivery hashes and the shared 32 KiB budget.

**Tech Stack:** Python 3.12, FastAPI, Pydantic AI, loguru, SQLModel, pytest.

## Global Constraints

- Load `~/AGENTS.md` as the lowest-precedence global baseline.
- Load `<project_root>/AGENTS.md` as project-wide guidance.
- Discover nested `AGENTS.md` files from touched filesystem paths; nearest file is last and highest precedence.
- Precedence: global -> project root -> nearest nested -> explicit user chat.
- Refresh global and project root on every user run.
- Refresh nested files only when their directory is touched again.
- Removal clears guidance; temporary read failure preserves the last known content.
- Shared 32 KiB session budget, allocated root -> nested -> global.
- Cap global content separately only through the shared budget; do not add a second cap.
- Exact filename `AGENTS.md` only; no `CLAUDE.md` or `AGENTS.override.md`.
- No watchers, UI indicators, session-detail metadata, or database migration.
- Reject symlink/path escapes for global, project, and nested files.
- Nested injection applies only to string-returning filesystem tools.
- Keep existing chat, ACP, A2A, skills, sub-session, and tool behavior intact.
- Run one backend package per pytest invocation.

---

### Task 1: Instruction-file loader and cache

**Files:**
- Create: `packages/agentbox-api/src/agentbox_api/project_instructions.py`
- Create: `packages/agentbox-api/tests/test_project_instructions.py`

**Interfaces:**
- Produces: `InstructionFile`, `global_instructions_path()`, `read_instruction_file()`, `load_global_instructions()`, `load_project_instructions()`, `load_nested_instructions()`.

- [ ] **Step 1: Write the failing tests**

```python
# packages/agentbox-api/tests/test_project_instructions.py
import pathlib

import pytest

from agentbox_api import project_instructions


def test_loads_project_root_file(tmp_path: pathlib.Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text("Run tests before commit.", encoding="utf-8")

    loaded = project_instructions.read_instruction_file(
        project / "AGENTS.md",
        boundary=project,
        source="AGENTS.md",
        scope="project",
        max_bytes=project_instructions.MAX_INSTRUCTION_BYTES,
    )

    assert loaded is not None
    assert loaded.content == "Run tests before commit."
    assert loaded.truncated is False


def test_ignores_missing_and_empty_files(tmp_path: pathlib.Path):
    project = tmp_path / "project"
    project.mkdir()
    assert (
        project_instructions.read_instruction_file(
            project / "AGENTS.md",
            boundary=project,
            source="AGENTS.md",
            scope="project",
            max_bytes=project_instructions.MAX_INSTRUCTION_BYTES,
        )
        is None
    )
    (project / "AGENTS.md").write_text("   \n", encoding="utf-8")
    assert (
        project_instructions.read_instruction_file(
            project / "AGENTS.md",
            boundary=project,
            source="AGENTS.md",
            scope="project",
            max_bytes=project_instructions.MAX_INSTRUCTION_BYTES,
        )
        is None
    )


def test_truncates_on_utf8_boundary_and_marks_truncated(tmp_path: pathlib.Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text("é" * 40, encoding="utf-8")

    loaded = project_instructions.read_instruction_file(
        project / "AGENTS.md",
        boundary=project,
        source="AGENTS.md",
        scope="project",
        max_bytes=31,
    )

    assert loaded is not None
    assert loaded.truncated is True
    assert len(loaded.content.encode("utf-8")) <= 31
    assert loaded.content.startswith("é")


def test_rejects_symlink_escape(tmp_path: pathlib.Path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    link = project / "AGENTS.md"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")

    assert (
        project_instructions.read_instruction_file(
            link,
            boundary=project,
            source="AGENTS.md",
            scope="project",
            max_bytes=project_instructions.MAX_INSTRUCTION_BYTES,
        )
        is None
    )


def test_read_failure_uses_last_known_content(tmp_path: pathlib.Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    agents = project / "AGENTS.md"
    agents.write_text("known guidance", encoding="utf-8")
    args = dict(
        boundary=project,
        source="AGENTS.md",
        scope="project",
        max_bytes=project_instructions.MAX_INSTRUCTION_BYTES,
    )
    first = project_instructions.read_instruction_file(agents, **args)
    assert first is not None and first.content == "known guidance"

    original_read = pathlib.Path.read_bytes

    def failing_read(self):
        if self == agents:
            raise OSError("temporary")
        return original_read(self)

    monkeypatch.setattr(pathlib.Path, "read_bytes", failing_read)
    second = project_instructions.read_instruction_file(agents, **args)
    assert second is not None
    assert second.content == "known guidance"


def test_global_path_uses_home(tmp_path: pathlib.Path, monkeypatch):
    monkeypatch.setattr(project_instructions, "global_instructions_path", lambda: tmp_path / "AGENTS.md")
    (tmp_path / "AGENTS.md").write_text("global", encoding="utf-8")
    loaded = project_instructions.load_global_instructions()
    assert loaded is not None and loaded.content == "global"
    assert loaded.source == "~/AGENTS.md"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
uv run pytest packages/agentbox-api/tests/test_project_instructions.py -q
```

Expected: FAIL with `ModuleNotFoundError` or missing attributes.

- [ ] **Step 3: Implement the loader**

```python
# packages/agentbox-api/src/agentbox_api/project_instructions.py
from __future__ import annotations

import hashlib
import pathlib
from dataclasses import dataclass

from loguru import logger

MAX_INSTRUCTION_BYTES = 32 * 1024
AGENTS_FILENAME = "AGENTS.md"

_content_cache: dict[pathlib.Path, str] = {}


@dataclass(frozen=True)
class InstructionFile:
    path: pathlib.Path
    source: str
    scope: str
    content: str
    truncated: bool = False


def global_instructions_path() -> pathlib.Path:
    return pathlib.Path.home() / AGENTS_FILENAME


def _truncate_utf8(text: str, limit: int) -> tuple[str, bool]:
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text, False
    cut = data[:limit]
    while cut:
        try:
            return cut.decode("utf-8"), True
        except UnicodeDecodeError:
            cut = cut[:-1]
    return "", True


def _inside(path: pathlib.Path, boundary: pathlib.Path) -> bool:
    return path == boundary or boundary in path.parents


def read_instruction_file(
    path: pathlib.Path,
    *,
    boundary: pathlib.Path,
    source: str,
    scope: str,
    max_bytes: int,
) -> InstructionFile | None:
    try:
        resolved = path.expanduser().resolve()
        boundary_resolved = boundary.expanduser().resolve()
    except OSError as exc:
        logger.warning("instruction path resolve failed path={} error={}", path, exc)
        return None
    if not _inside(resolved, boundary_resolved):
        logger.warning("instruction path escapes boundary path={} boundary={}", resolved, boundary_resolved)
        return None
    try:
        raw = resolved.read_bytes()
    except FileNotFoundError:
        _content_cache.pop(resolved, None)
        return None
    except OSError as exc:
        cached = _content_cache.get(resolved)
        if cached is None:
            logger.warning("instruction read failed path={} error={}", resolved, exc)
            return None
        logger.warning("instruction read failed; using cached content path={} error={}", resolved, exc)
        text = cached
    else:
        text = raw.decode("utf-8", errors="replace")
        if not text.strip():
            _content_cache.pop(resolved, None)
            return None
        _content_cache[resolved] = text
    content, truncated = _truncate_utf8(text, max_bytes)
    if not content.strip():
        return None
    return InstructionFile(
        path=resolved,
        source=source,
        scope=scope,
        content=content,
        truncated=truncated,
    )


def load_global_instructions() -> InstructionFile | None:
    path = global_instructions_path()
    return read_instruction_file(
        path,
        boundary=path.parent,
        source="~/AGENTS.md",
        scope="global",
        max_bytes=MAX_INSTRUCTION_BYTES,
    )


def load_project_instructions(project_root: str) -> InstructionFile | None:
    root = pathlib.Path(project_root).expanduser().resolve()
    return read_instruction_file(
        root / AGENTS_FILENAME,
        boundary=root,
        source="AGENTS.md",
        scope="project",
        max_bytes=MAX_INSTRUCTION_BYTES,
    )


def load_nested_instructions(project_root: str, path: pathlib.Path) -> InstructionFile | None:
    root = pathlib.Path(project_root).expanduser().resolve()
    try:
        source = path.resolve().relative_to(root).as_posix()
    except ValueError:
        return None
    return read_instruction_file(
        path,
        boundary=root,
        source=source,
        scope="nested",
        max_bytes=MAX_INSTRUCTION_BYTES,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```powershell
uv run pytest packages/agentbox-api/tests/test_project_instructions.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-api/src/agentbox_api/project_instructions.py packages/agentbox-api/tests/test_project_instructions.py
git commit -m "feat(api): load AGENTS.md instruction files"
```

---

### Task 2: Session state, budget, and system-prompt block

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/project_instructions.py`
- Modify: `packages/agentbox-api/tests/test_project_instructions.py`

**Interfaces:**
- Produces: `InstructionState`, `get_instruction_state(session_id)`, `clear_instruction_state(session_id)`, `build_system_instruction_block(project_root, session_id)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_system_block_orders_global_before_project(tmp_path: pathlib.Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text("project rules", encoding="utf-8")
    monkeypatch.setattr(project_instructions, "global_instructions_path", lambda: tmp_path / "AGENTS.md")
    (tmp_path / "AGENTS.md").write_text("global rules", encoding="utf-8")

    block = project_instructions.build_system_instruction_block(str(project), "s1")
    assert block.index("global rules") < block.index("project rules")
    assert 'source="~/AGENTS.md"' in block
    assert 'source="AGENTS.md"' in block


def test_system_block_root_priority_over_global(tmp_path: pathlib.Path, monkeypatch, caplog):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(project_instructions, "MAX_INSTRUCTION_BYTES", 10)
    (project / "AGENTS.md").write_text("1234567890", encoding="utf-8")
    monkeypatch.setattr(project_instructions, "global_instructions_path", lambda: tmp_path / "AGENTS.md")
    (tmp_path / "AGENTS.md").write_text("global", encoding="utf-8")

    block = project_instructions.build_system_instruction_block(str(project), "s2")
    assert "1234567890" in block
    assert "global" not in block


def test_removing_root_clears_it_on_next_build(tmp_path: pathlib.Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    agents = project / "AGENTS.md"
    agents.write_text("root rules", encoding="utf-8")
    monkeypatch.setattr(project_instructions, "global_instructions_path", lambda: tmp_path / "missing-global.md")
    first = project_instructions.build_system_instruction_block(str(project), "s3")
    assert "root rules" in first
    agents.unlink()
    second = project_instructions.build_system_instruction_block(str(project), "s3")
    assert "root rules" not in second


def test_clear_state_releases_session(tmp_path: pathlib.Path):
    state = project_instructions.get_instruction_state("s4")
    state.nested_bytes = 123
    project_instructions.clear_instruction_state("s4")
    assert project_instructions.get_instruction_state("s4").nested_bytes == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
uv run pytest packages/agentbox-api/tests/test_project_instructions.py -q
```

Expected: FAIL because the state and builder do not exist.

- [ ] **Step 3: Implement the state and builder**

Add:

```python
@dataclass
class InstructionState:
    root_hash: str | None = None
    global_hash: str | None = None
    root_bytes: int = 0
    nested_bytes: int = 0
    delivered: dict[pathlib.Path, str] = field(default_factory=dict)


_states: dict[str, InstructionState] = {}


def get_instruction_state(session_id: str | None) -> InstructionState:
    if session_id is None:
        return InstructionState()
    return _states.setdefault(session_id, InstructionState())


def clear_instruction_state(session_id: str) -> None:
    _states.pop(session_id, None)


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _block(file: InstructionFile, content: str, truncated: bool) -> str:
    suffix = "\n\n[Truncated to fit the shared 32 KiB instruction budget.]" if truncated else ""
    return (
        f'<project_instructions source="{file.source}" scope="{file.scope}">\n'
        f"{content.strip()}{suffix}\n</project_instructions>"
    )


def build_system_instruction_block(project_root: str, session_id: str | None) -> str:
    state = get_instruction_state(session_id)
    root = load_project_instructions(project_root)
    global_file = load_global_instructions()
    blocks: list[str] = []

    root_content = root.content if root else ""
    root_bytes = len(root_content.encode("utf-8"))
    state.root_bytes = root_bytes
    state.root_hash = _digest(root_content) if root else None
    if root:
        blocks.append(_block(root, root_content, root.truncated))

    nested_reserved = min(state.nested_bytes, MAX_INSTRUCTION_BYTES)
    remaining = max(MAX_INSTRUCTION_BYTES - root_bytes - nested_reserved, 0)
    if global_file:
        global_content, global_truncated = _truncate_utf8(global_file.content, remaining)
        state.global_hash = _digest(global_file.content)
        if global_content.strip():
            blocks.insert(
                0,
                _block(global_file, global_content, global_truncated or global_file.truncated),
            )
        else:
            blocks.insert(
                0,
                '<project_instructions source="~/AGENTS.md" scope="global">'
                "Global instructions omitted: shared 32 KiB budget exhausted."
                "</project_instructions>",
            )
    else:
        state.global_hash = None

    if not blocks:
        return ""
    return (
        "Project instructions follow. Explicit user messages override them.\n\n"
        + "\n\n".join(blocks)
    )
```

Add `from dataclasses import dataclass, field`.

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```powershell
uv run pytest packages/agentbox-api/tests/test_project_instructions.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-api/src/agentbox_api/project_instructions.py packages/agentbox-api/tests/test_project_instructions.py
git commit -m "feat(api): budget AGENTS.md system instructions"
```

---

### Task 3: Nested discovery and tool hook

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/project_instructions.py`
- Modify: `packages/agentbox-api/tests/test_project_instructions.py`

**Interfaces:**
- Produces: `discover_nested_agents(project_root, target) -> list[pathlib.Path]`, `make_project_instructions_hook(project_root, session_id)`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_discovers_nested_nearest_last(tmp_path: pathlib.Path):
    project = tmp_path / "project"
    (project / "pkg" / "web").mkdir(parents=True)
    (project / "AGENTS.md").write_text("root", encoding="utf-8")
    (project / "pkg" / "AGENTS.md").write_text("pkg", encoding="utf-8")
    (project / "pkg" / "web" / "AGENTS.md").write_text("web", encoding="utf-8")

    found = project_instructions.discover_nested_agents(str(project), "pkg/web/app.ts")
    assert [path.name for path in found] == ["AGENTS.md", "AGENTS.md", "AGENTS.md"]
    assert [path.parent.name for path in found] == ["pkg", "web"]


async def test_nested_hook_emits_nearest_last_and_dedupes(tmp_path: pathlib.Path):
    project = tmp_path / "project"
    (project / "pkg").mkdir(parents=True)
    (project / "pkg" / "AGENTS.md").write_text("pkg rules", encoding="utf-8")
    hook = project_instructions.make_project_instructions_hook(str(project), "s1")
    ctx = ToolHookContext(
        tool_name="read_text_file",
        args={"path": "pkg/file.txt"},
        root=project,
        result="file content",
    )
    first = await hook(ctx)
    assert first is not None and "pkg rules" in first
    second = await hook(ctx)
    assert second is None


async def test_nested_hook_reemits_changed_file(tmp_path: pathlib.Path):
    project = tmp_path / "project"
    (project / "pkg").mkdir(parents=True)
    agents = project / "pkg" / "AGENTS.md"
    agents.write_text("old", encoding="utf-8")
    hook = project_instructions.make_project_instructions_hook(str(project), "s1")
    ctx = ToolHookContext("read_text_file", {"path": "pkg/file.txt"}, project, "content")
    assert "old" in (await hook(ctx) or "")
    agents.write_text("new", encoding="utf-8")
    updated = await hook(ctx)
    assert updated is not None and "new" in updated


async def test_nested_hook_removal_notice(tmp_path: pathlib.Path):
    project = tmp_path / "project"
    (project / "pkg").mkdir(parents=True)
    agents = project / "pkg" / "AGENTS.md"
    agents.write_text("pkg rules", encoding="utf-8")
    hook = project_instructions.make_project_instructions_hook(str(project), "s1")
    ctx = ToolHookContext("read_text_file", {"path": "pkg/file.txt"}, project, "content")
    assert await hook(ctx) is not None
    agents.unlink()
    removed = await hook(ctx)
    assert removed is not None and "no longer applies" in removed
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
uv run pytest packages/agentbox-api/tests/test_project_instructions.py -q
```

Expected: FAIL because discovery and hook do not exist.

- [ ] **Step 3: Implement discovery and hook**

```python
NESTED_TOOLS = {
    "read_text_file",
    "read_file",
    "read_multiple_files",
    "list_directory",
    "list_directory_with_sizes",
    "search_files",
    "write_file",
    "append_file",
    "edit_file",
    "create_directory",
    "move_file",
    "copy_file",
    "delete_path",
}


def _target_paths(tool_name: str, args: dict) -> list[str]:
    if "paths" in args and isinstance(args["paths"], list):
        return [str(value) for value in args["paths"]]
    if tool_name in {"move_file", "copy_file"}:
        return [str(value) for value in (args.get("source"), args.get("destination")) if value]
    path = args.get("path")
    return [str(path)] if path else []


def discover_nested_agents(project_root: str, target: str) -> list[pathlib.Path]:
    root = pathlib.Path(project_root).expanduser().resolve()
    candidate = pathlib.Path(target).expanduser()
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if not _inside(resolved, root):
        return []
    current = resolved if resolved.is_dir() else resolved.parent
    found: list[pathlib.Path] = []
    while current != root and root in current.parents:
        agents = current / AGENTS_FILENAME
        if agents.is_file():
            found.append(agents)
        current = current.parent
    return list(reversed(found))


def make_project_instructions_hook(project_root: str, session_id: str):
    async def hook(ctx) -> str | None:
        if ctx.tool_name not in NESTED_TOOLS or not isinstance(ctx.result, str):
            return None
        state = get_instruction_state(session_id)
        root = pathlib.Path(project_root).expanduser().resolve()
        targets = _target_paths(ctx.tool_name, ctx.args)
        blocks: list[str] = []
        seen: set[pathlib.Path] = set()
        ancestor_dirs: set[pathlib.Path] = set()

        for target in targets:
            candidate = pathlib.Path(target).expanduser()
            resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
            if not _inside(resolved, root):
                continue
            current = resolved if resolved.is_dir() else resolved.parent
            while current != root and root in current.parents:
                ancestor_dirs.add(current)
                current = current.parent
            for path in discover_nested_agents(project_root, target):
                if path in seen:
                    continue
                seen.add(path)
                loaded = load_nested_instructions(project_root, path)
                if loaded is None:
                    continue
                digest = _digest(loaded.content)
                if state.delivered.get(path) == digest:
                    continue
                remaining = max(
                    MAX_INSTRUCTION_BYTES - state.root_bytes - state.nested_bytes,
                    0,
                )
                content, truncated = _truncate_utf8(loaded.content, remaining)
                if not content.strip():
                    blocks.append(
                        f'<project_instructions source="{loaded.source}" scope="nested">'
                        "Nested instructions omitted: shared 32 KiB budget exhausted."
                        "</project_instructions>"
                    )
                    continue
                state.delivered[path] = digest
                state.nested_bytes += len(content.encode("utf-8"))
                blocks.append(_block(loaded, content, truncated or loaded.truncated))

        for path in list(state.delivered):
            if path.parent in ancestor_dirs and not path.is_file():
                blocks.append(
                    f'<project_instructions source="{path.relative_to(root).as_posix()}" '
                    'scope="nested">This nested AGENTS.md no longer applies.</project_instructions>'
                )
                state.nested_bytes = max(
                    0, state.nested_bytes - len(_content_cache.get(path, "").encode("utf-8"))
                )
                state.delivered.pop(path, None)
        return "\n\n".join(blocks) or None

    return hook
```

Import `ToolHookContext` for the type in tests and the hook annotation. If the annotation imports from `agentbox_harness.tools.registry`, use:

```python
from agentbox_harness.tools.registry import ToolHookContext
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```powershell
uv run pytest packages/agentbox-api/tests/test_project_instructions.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-api/src/agentbox_api/project_instructions.py packages/agentbox-api/tests/test_project_instructions.py
git commit -m "feat(api): discover nested AGENTS.md files"
```

---

### Task 4: Wire prepare_agent, subagents, and cleanup

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/skills.py`
- Modify: `packages/agentbox-api/src/agentbox_api/runtime.py`
- Modify: `packages/agentbox-api/tests/test_skills.py`
- Modify: `packages/agentbox-api/tests/test_project_instructions.py`

**Interfaces:**
- Consumes: `build_system_instruction_block`, `make_project_instructions_hook`, `clear_instruction_state`.
- Produces: root/global guidance in `PreparedAgent.spec.instructions`; nested hook registered with the tool registry; state cleanup in `delete_session_data`.

- [ ] **Step 1: Write the failing integration tests**

Add to `test_project_instructions.py`:

```python
async def test_prepare_agent_injects_root_and_global(tmp_path: pathlib.Path, monkeypatch):
    from agentbox_api.skills import prepare_agent
    from agentbox_api.security import hash_password
    from agentbox_models.db import create_engine_and_sessionmaker, init_db
    from agentbox_models.tables.auth import Permission, Role, RolePermissionLink, User, UserRoleLink
    from agentbox_models.tables.core import Agent, Model, Project, Provider, SessionRow

    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text("root rules", encoding="utf-8")
    monkeypatch.setattr(project_instructions, "global_instructions_path", lambda: tmp_path / "AGENTS.md")
    (tmp_path / "AGENTS.md").write_text("global rules", encoding="utf-8")

    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(User(id="u1", username="alice", email="a@x", password_hash=hash_password("pw")))
        s.add(Role(id="r1", name="role"))
        s.add(Permission(id="p0", name="sessions:create"))
        s.add(RolePermissionLink(role_id="r1", permission_id="p0"))
        s.add(UserRoleLink(user_id="u1", role_id="r1"))
        s.add(Provider(id="prov", name="test", kind="test"))
        s.add(Model(id="m", provider_id="prov", name="test-model"))
        s.add(Agent(id="ag", name="bot", description="", instructions="base", model_id="m"))
        s.add(Project(id="prj", name="p", path=str(project), owner_id="u1"))
        s.add(SessionRow(id="s1", project_id="prj", agent_id="ag"))
        await s.commit()

    prepared = await prepare_agent(
        factory, "bot", str(project), str(tmp_path / "skills"), session_id="s1"
    )
    assert "global rules" in prepared.spec.instructions
    assert "root rules" in prepared.spec.instructions
    assert prepared.spec.instructions.index("global rules") < prepared.spec.instructions.index("root rules")
    await engine.dispose()


async def test_prepare_agent_reregisters_nested_on_read(tmp_path: pathlib.Path, monkeypatch):
    from agentbox_api.skills import prepare_agent
    from agentbox_harness.spec import Mode
    from agentbox_models.db import create_engine_and_sessionmaker, init_db
    from agentbox_models.tables.core import Agent, Model, Project, Provider, SessionRow

    monkeypatch.setattr(
        project_instructions,
        "global_instructions_path",
        lambda: tmp_path / "missing-global.md",
    )
    project = tmp_path / "project"
    (project / "pkg").mkdir(parents=True)
    (project / "pkg" / "AGENTS.md").write_text("pkg rules", encoding="utf-8")
    (project / "pkg" / "file.txt").write_text("content", encoding="utf-8")

    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
        s.add(Provider(id="prov", name="test", kind="test"))
        s.add(Model(id="m", provider_id="prov", name="test-model"))
        s.add(Agent(id="ag", name="bot", description="", instructions="base", model_id="m"))
        s.add(Project(id="prj", name="p", path=str(project), owner_id="u1"))
        s.add(SessionRow(id="s1", project_id="prj", agent_id="ag"))
        await s.commit()

    prepared = await prepare_agent(factory, "bot", str(project), str(tmp_path / "skills"), session_id="s1")
    tools = prepared.registry.select_tools(Mode(name="agent", flags={"write": True}))
    read_tool = next(tool for tool in tools if tool.__name__ == "read_text_file")
    output = await read_tool("pkg/file.txt")
    assert "pkg rules" in output
    await engine.dispose()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
uv run pytest packages/agentbox-api/tests/test_project_instructions.py -q
```

Expected: FAIL because `prepare_agent` does not inject or register the hook.

- [ ] **Step 3: Wire the loader and hook**

In `skills.py`:

```python
from agentbox_api.project_instructions import (
    build_system_instruction_block,
    make_project_instructions_hook,
)
```

After `spec = augment_spec(spec, skills)`:

```python
instruction_block = build_system_instruction_block(project_root, session_id)
if instruction_block:
    spec = spec.model_copy(
        update={"instructions": spec.instructions + "\n\n" + instruction_block}
    )
```

In the hooks section:

```python
if session_id:
    hooks.append(make_project_instructions_hook(project_root, session_id))
```

Place this before `build_registry` so the hook wraps tools.

In `runtime.py` `delete_session_data`, call:

```python
from agentbox_api.project_instructions import clear_instruction_state

await clear_instruction_state(session_id)
```

Place it at the start of `delete_session_data`, before deleting rows.

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```powershell
uv run pytest packages/agentbox-api/tests/test_project_instructions.py -q
uv run pytest packages/agentbox-api/tests/test_skills.py -q
uv run pytest packages/agentbox-api/tests/test_chat.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-api/src/agentbox_api/skills.py packages/agentbox-api/src/agentbox_api/runtime.py packages/agentbox-api/tests/test_project_instructions.py packages/agentbox-api/tests/test_skills.py
git commit -m "feat(api): inject AGENTS.md guidance into agents"
```

---

### Task 5: Roadmap, final verification, and merge

**Files:**
- Modify: `docs/ROADMAP.md`
- Modify: `docs/superpowers/specs/2026-11-21-agents-md-project-instructions-design.md`
- Modify: `docs/superpowers/plans/2026-11-21-agents-md-project-instructions.md`

**Interfaces:**
- Produces: completed D20 evolution on `master`.

- [ ] **Step 1: Update roadmap and statuses**

- Remove D20 from the deferred backlog.
- Add history row 34: `AGENTS.md project instructions` with the spec and plan paths.
- Update the completion paragraph to include D20.
- Add `**Status:** COMPLETE` to the plan.
- Change the spec status to `Approved`.

- [ ] **Step 2: Run all checks**

```powershell
uv run pytest packages/agentbox-api -q
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-providers -q
uv run ruff check --fix packages
uv run ty check packages
cd apps/web
bun run test
bun run build
bun run e2e
```

Expected: all pass; no DB migration or screenshot work.

- [ ] **Step 3: Commit docs**

```powershell
git add docs/ROADMAP.md docs/superpowers/specs/2026-11-21-agents-md-project-instructions-design.md docs/superpowers/plans/2026-11-21-agents-md-project-instructions.md
git commit -m "docs: complete D20 AGENTS.md instructions"
```

- [ ] **Step 4: Merge into master**

```powershell
git switch master
git merge --ff-only feat/agents-md-instructions
git status --short
```

Expected: fast-forward merge and clean working tree.

---

## Self-review

**Spec coverage:** Task 1 covers global/root loading, truncation, cache, and symlink safety. Task 2 covers state and root -> nested -> global budgeting. Task 3 covers nested discovery, delivery, dedupe, changes, and removal. Task 4 wires root/global injection, the nested hook, sub-session inheritance through `prepare_agent`, and cleanup. Task 5 covers documentation, full verification, and merge.

**Placeholder scan:** No TBD/TODO steps; each task names files, tests, commands, and commits.

**Type consistency:** `InstructionFile`, `InstructionState`, `read_instruction_file`, `load_global_instructions`, `load_project_instructions`, `load_nested_instructions`, `discover_nested_agents`, `make_project_instructions_hook`, `build_system_instruction_block`, `get_instruction_state`, and `clear_instruction_state` keep the same names across tasks.
