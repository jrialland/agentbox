# Streaming

A run streams over AG-UI server-sent events from `POST /sessions/{sid}/messages`.

## Request

```bash
curl -N -X POST "$AGENTBOX_URL/sessions/$SESSION_ID/messages" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"content": "Explain the project layout.", "mode": "agent"}'
```

`-N` disables client buffering. The response is `text/event-stream`; each `data:` frame is a JSON AG-UI event.

## Event lifecycle

A successful run starts with `RUN_STARTED` and ends with `RUN_FINISHED`. A failed run ends with `RUN_ERROR`. Between them, expect:

- `TEXT_MESSAGE_START`, `TEXT_MESSAGE_CONTENT`, `TEXT_MESSAGE_END` for assistant output.
- `REASONING_MESSAGE_START`, `REASONING_MESSAGE_CONTENT`, `REASONING_MESSAGE_END` for visible reasoning.
- `TOOL_CALL_START`, `TOOL_CALL_ARGS`, `TOOL_CALL_END`, `TOOL_CALL_RESULT` for tool activity.
- `STEP_STARTED` and `STEP_FINISHED` for loop steps.
- `CUSTOM` with name `mcp.warning` when an MCP server fails to start; the turn continues.

The assistant turn is persisted after the run reaches a terminal event. Consume the stream to completion before closing the connection so persistence can finish.

## Client rules

- Keep reading until `RUN_FINISHED` or `RUN_ERROR`; do not poll history while the stream is open.
- Treat `RUN_ERROR` as a failed turn and surface the error message.
- To stop a run, call `POST /sessions/{sid}/messages/cancel` rather than only closing the connection.
- Send one active message per session at a time.
