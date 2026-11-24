"""Render Jinja2 prompt templates for agent and project configuration.

Templates are trusted text authored by users or agent configurations and are
rendered to plain prompt strings, never to HTML. Rendering uses a
:class:`~jinja2.sandbox.SandboxedEnvironment`, which blocks unsafe attribute
access, but autoescaping is disabled because the output is not HTML; callers
must not inject rendered output into HTML without escaping it themselves.
Missing variables are reported, not fatal.
"""

import pathlib
from datetime import UTC, datetime

from jinja2 import ChainableUndefined, TemplateError, meta
from jinja2.sandbox import SandboxedEnvironment
from loguru import logger

# Autoescape stays off: prompt text is not markup. The sandbox still restricts
# what template authors can reach through the context.
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
    """Raised when a prompt template cannot be parsed or rendered.

    Attributes:
        message: The underlying Jinja2 error text.
        agent: Optional agent name the template belongs to, for reporting.
        line: Optional template line number where the error occurred.
    """

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
    """Build the template context for a session's prompt rendering.

    Args:
        agent_name: Agent configuration name.
        agent_description: Agent configuration description.
        project_root: Project root path; its basename becomes the project name.
        user_name: Session user's username, or ``None`` to render empty.
        session_id: Session id, or ``None`` to render empty.
        session_mode: Session mode, or ``None`` to render empty.
        model_name: Resolved model name.
        model_provider: Provider of the resolved model.
        skills: Iterable of skill objects exposing ``name`` and
            ``description``; rendered as a list of mappings.
        now: Timestamp used for date/time fields. Defaults to the current UTC
            time.

    Returns:
        A nested context mapping matching the variables referenced by prompt
        templates.
    """
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
    """Render a prompt template, warning about undeclared variables first.

    Undefined variables render through ``ChainableUndefined`` and are logged,
    not raised; only parse or render errors become
    :class:`PromptTemplateError`.

    Args:
        template: Jinja2 template source.
        context: Variable mapping passed to the template.
        agent: Optional agent name used in warnings and error reporting.

    Returns:
        The rendered prompt text.

    Raises:
        PromptTemplateError: If the template cannot be parsed or rendered.
    """
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
    """Render a template against sample data for editor previews.

    Unlike :func:`render_prompt`, template errors are captured into the result
    instead of raised, so a half-written template still yields a response.
    Overrides with keys outside the preview variables are ignored.

    Args:
        template: Jinja2 template source.
        overrides: Optional flat values replacing entries in
            :data:`PREVIEW_CONTEXT`.

    Returns:
        A mapping with the rendered text, missing variables, an error object or
        ``None``, the flat context used, and the known variable names.
    """
    flat = dict(PREVIEW_CONTEXT)
    flat.update(
        {key: value for key, value in (overrides or {}).items() if key in flat}
    )
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
