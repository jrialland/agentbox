from agentbox_api.streaming import agui_response


async def test_agui_response_is_streaming():
    async def events():
        if False:
            yield None

    resp = agui_response(events())
    assert resp.status_code == 200
    assert "event-stream" in resp.media_type
