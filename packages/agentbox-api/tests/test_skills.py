import pathlib

from agentbox_api.skills import augment_spec, discover_skills, make_activate_tool
from agentbox_harness.spec import AgentSpec, ModelBinding, NativeToolBinding


def _write_skill(dir_: pathlib.Path, name: str, desc: str, body: str) -> None:
    d = dir_ / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n{body}\n", encoding="utf-8"
    )


def test_discovery_precedence(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    pdir = project / ".agents" / "skills"
    pdir.mkdir(parents=True)
    user = tmp_path / "user"
    user.mkdir()
    _write_skill(pdir, "shared", "project version", "project body")
    _write_skill(user, "shared", "user version", "user body")
    _write_skill(user, "only-user", "user only", "u body")

    skills = discover_skills(str(project), str(user))
    by = {s.name: s for s in skills}
    assert by["shared"].scope == "project"
    assert by["shared"].description == "project version"
    assert by["only-user"].scope == "user"
    assert "commit-message" in by and by["commit-message"].scope == "builtin"


def test_augment_and_activate(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _write_skill(project / ".agents" / "skills", "demo", "d", "# Demo\nDo it.")
    skills = discover_skills(str(project), str(tmp_path / "missing"))

    spec = AgentSpec(
        name="a",
        description="",
        instructions="base",
        tool_bindings=[],
        model_binding=ModelBinding(model="test", provider="test"),
    )
    augmented = augment_spec(spec, skills)
    assert "available_skills" in augmented.instructions
    assert any(
        isinstance(b, NativeToolBinding) and b.name == "activate_skill"
        for b in augmented.tool_bindings
    )

    import asyncio

    tool = make_activate_tool(skills)
    out = asyncio.run(tool("demo"))
    assert "Do it." in out and "Skill directory" in out
