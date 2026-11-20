from pydantic_ai.usage import RequestUsage

from agentbox_harness.usage import context_tokens_from_usage


def test_context_tokens_from_measured_usage():
    usage = RequestUsage(input_tokens=10, output_tokens=5)
    assert context_tokens_from_usage(usage) == 15


def test_context_tokens_from_unmeasured_usage():
    assert context_tokens_from_usage(RequestUsage()) is None
