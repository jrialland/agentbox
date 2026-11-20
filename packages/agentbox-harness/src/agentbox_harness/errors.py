from dataclasses import dataclass

from pydantic_ai.exceptions import ModelContextWindowExceededError, RunCancelled

from agentbox_harness.tools.filesystem import PathEscapesRootError


@dataclass(frozen=True)
class RunOutcome:
    status: str  # "success" | "cancelled" | "error"
    message: str | None = None
    code: str | None = None


def normalize_error(exc: BaseException) -> RunOutcome:
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
