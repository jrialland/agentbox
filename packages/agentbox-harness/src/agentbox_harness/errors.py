"""Normalize exceptions raised during a run into a run outcome."""

from dataclasses import dataclass

from pydantic_ai.exceptions import ModelContextWindowExceededError, RunCancelled

from agentbox_harness.tools.filesystem import PathEscapesRootError


@dataclass(frozen=True)
class RunOutcome:
    """Terminal status and optional detail for a run.

    ``status`` is one of ``"success"``, ``"cancelled"``, or ``"error"``.
    """

    status: str  # "success" | "cancelled" | "error"
    message: str | None = None
    code: str | None = None


def normalize_error(exc: BaseException) -> RunOutcome:
    """Map a run exception to a stable :class:`RunOutcome`.

    Cancellations, context-window overflows, and path-escape errors map to
    specific statuses or codes; any other exception becomes a generic error.

    Args:
        exc: Exception raised while running a session.

    Returns:
        The normalized outcome for the exception.
    """
    if isinstance(exc, RunCancelled):
        return RunOutcome(status="cancelled", message=str(exc))
    if isinstance(exc, ModelContextWindowExceededError):
        return RunOutcome(
            status="error",
            message=str(exc),
            code="context_window",
        )
    if isinstance(exc, PathEscapesRootError):
        return RunOutcome(status="error", message=f"Path escapes project root: {exc}")
    return RunOutcome(status="error", message=str(exc))
