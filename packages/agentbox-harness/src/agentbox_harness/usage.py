"""Helpers for reading token usage from pydantic-ai runs."""

from pydantic_ai.usage import RequestUsage


def context_tokens_from_usage(usage: RequestUsage) -> int | None:
    """Return total tokens for a request usage, or ``None`` when unset.

    Args:
        usage: Request usage reported by the model backend.

    Returns:
        The total token count, or ``None`` when the usage has no values.
    """
    return usage.total_tokens if usage.has_values() else None
