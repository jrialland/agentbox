from pydantic_ai.usage import RequestUsage


def context_tokens_from_usage(usage: RequestUsage) -> int | None:
    return usage.total_tokens if usage.has_values() else None
