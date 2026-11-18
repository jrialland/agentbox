from pydantic_ai.ui.ag_ui import AGUIEventStream

from agentbox_harness.errors import RunOutcome


async def _unwrap(run_events):
    async for re in run_events:
        if isinstance(re.event, RunOutcome):
            continue
        yield re.event


def agui_response(run_events):
    stream = AGUIEventStream()
    agui = stream.transform_stream(_unwrap(run_events))
    return stream.streaming_response(agui)
