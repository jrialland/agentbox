from agentbox_api.templating import build_context, preview_prompt, render_prompt


def test_render_interpolates_and_filters():
    ctx = {"user": {"username": "Alice"}, "skills": [{"name": "a", "description": ""}]}
    assert render_prompt("Hi {{ user.username|lower }}", ctx) == "Hi alice"
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


def test_environment_is_sandboxed():
    from jinja2.sandbox import SandboxedEnvironment

    from agentbox_api.templating import ENV

    assert isinstance(ENV, SandboxedEnvironment)


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
