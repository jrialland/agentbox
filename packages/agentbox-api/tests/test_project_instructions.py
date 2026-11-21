import pathlib

import pytest

from agentbox_api import project_instructions
from agentbox_harness.tools.registry import ToolHookContext


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


def test_read_failure_uses_last_known_content(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
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


def test_global_path_uses_home(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        project_instructions,
        "global_instructions_path",
        lambda: tmp_path / "AGENTS.md",
    )
    (tmp_path / "AGENTS.md").write_text("global", encoding="utf-8")
    loaded = project_instructions.load_global_instructions()
    assert loaded is not None and loaded.content == "global"
    assert loaded.source == "~/AGENTS.md"


def test_system_block_orders_global_before_project(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text("project rules", encoding="utf-8")
    monkeypatch.setattr(
        project_instructions,
        "global_instructions_path",
        lambda: tmp_path / "AGENTS.md",
    )
    (tmp_path / "AGENTS.md").write_text("global rules", encoding="utf-8")

    block = project_instructions.build_system_instruction_block(str(project), "s1")
    assert block.index("global rules") < block.index("project rules")
    assert 'source="~/AGENTS.md"' in block
    assert 'source="AGENTS.md"' in block


def test_system_block_root_priority_over_global(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(project_instructions, "MAX_INSTRUCTION_BYTES", 10)
    (project / "AGENTS.md").write_text("1234567890", encoding="utf-8")
    monkeypatch.setattr(
        project_instructions,
        "global_instructions_path",
        lambda: tmp_path / "AGENTS.md",
    )
    (tmp_path / "AGENTS.md").write_text("global", encoding="utf-8")

    block = project_instructions.build_system_instruction_block(str(project), "s2")
    assert "1234567890" in block
    assert "Global instructions omitted" in block


def test_removing_root_clears_it_on_next_build(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
    project = tmp_path / "project"
    project.mkdir()
    agents = project / "AGENTS.md"
    agents.write_text("root rules", encoding="utf-8")
    monkeypatch.setattr(
        project_instructions,
        "global_instructions_path",
        lambda: tmp_path / "missing-global.md",
    )
    first = project_instructions.build_system_instruction_block(str(project), "s3")
    assert "root rules" in first
    agents.unlink()
    second = project_instructions.build_system_instruction_block(str(project), "s3")
    assert "root rules" not in second


def test_clear_state_releases_session():
    state = project_instructions.get_instruction_state("s4")
    state.nested_bytes = 123
    project_instructions.clear_instruction_state("s4")
    assert project_instructions.get_instruction_state("s4").nested_bytes == 0


async def test_discovers_nested_nearest_last(tmp_path: pathlib.Path):
    project = tmp_path / "project"
    (project / "pkg" / "web").mkdir(parents=True)
    (project / "AGENTS.md").write_text("root", encoding="utf-8")
    (project / "pkg" / "AGENTS.md").write_text("pkg", encoding="utf-8")
    (project / "pkg" / "web" / "AGENTS.md").write_text("web", encoding="utf-8")

    found = project_instructions.discover_nested_agents(
        str(project), "pkg/web/app.ts"
    )
    assert [path.name for path in found] == ["AGENTS.md", "AGENTS.md"]
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
    ctx = ToolHookContext(
        "read_text_file", {"path": "pkg/file.txt"}, project, "content"
    )
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
    ctx = ToolHookContext(
        "read_text_file", {"path": "pkg/file.txt"}, project, "content"
    )
    assert await hook(ctx) is not None
    agents.unlink()
    removed = await hook(ctx)
    assert removed is not None and "no longer applies" in removed


async def test_prepare_agent_injects_root_and_global(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
    from agentbox_api.skills import prepare_agent
    from agentbox_models.db import create_engine_and_sessionmaker, init_db
    from agentbox_models.tables.core import Agent, Model, Project, Provider, SessionRow

    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text("root rules", encoding="utf-8")
    monkeypatch.setattr(
        project_instructions,
        "global_instructions_path",
        lambda: tmp_path / "AGENTS.md",
    )
    (tmp_path / "AGENTS.md").write_text("global rules", encoding="utf-8")

    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with factory() as s:
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
    assert prepared.spec.instructions.index("global rules") < prepared.spec.instructions.index(
        "root rules"
    )
    project_instructions.clear_instruction_state("s1")
    await engine.dispose()


async def test_prepare_agent_registers_nested_hook(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
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
        s.add(SessionRow(id="s2", project_id="prj", agent_id="ag"))
        await s.commit()

    prepared = await prepare_agent(
        factory, "bot", str(project), str(tmp_path / "skills"), session_id="s2"
    )
    tools = prepared.registry.select_tools(Mode(name="agent", flags={"write": True}))
    read_tool = next(tool for tool in tools if tool.__name__ == "read_text_file")
    output = await read_tool("pkg/file.txt")
    assert "pkg rules" in output
    project_instructions.clear_instruction_state("s2")
    await engine.dispose()
