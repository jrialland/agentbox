"""Translate harness run events into an AG-UI streaming HTTP response.

The flow of events is preserved in order: each non-terminal event emitted by
the run is forwarded to the AG-UI event stream, which encodes the terminal
message into the protocol's closing events. The harness's own terminal
``RunOutcome`` event is filtered out because it is internal bookkeeping, not an
AG-UI message.
"""

from pydantic_ai.ui.ag_ui import AGUIEventStream

from agentbox_harness.errors import RunOutcome


async def _unwrap(run_events):
    """Yield the underlying events while dropping internal terminal outcomes.

    ``RunOutcome`` marks the end of a run for the API's own bookkeeping but is
    not part of the AG-UI protocol, so it must not be forwarded to the client.
    """
    async for re in run_events:
        if isinstance(re.event, RunOutcome):
            continue
        yield re.event


def agui_response(run_events):
    """Wrap an async run-event generator as an AG-UI streaming response.

    Events are transformed in emission order. The response closes with the
    AG-UI protocol's terminal events; callers must not emit further run events
    after the stream ends.

    Args:
        run_events: Async iterable of harness run events.

    Returns:
        A streaming HTTP response carrying AG-UI encoded events.
    """
    stream = AGUIEventStream()
    agui = stream.transform_stream(_unwrap(run_events))
    return stream.streaming_response(agui)
