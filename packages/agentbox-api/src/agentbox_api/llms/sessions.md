# Sessions

A session is a live instance of an agent configuration on a project directory. It stores the conversation tree and run state. Child sessions started by the running agent are **subagent sessions**.

## Lifecycle

- `POST /sessions` with `{"project_id": "<id>", "agent_id": "<agent name>"}`. Despite the field name, `agent_id` carries the agent configuration name.
- `GET /sessions` lists root sessions. Subagent sessions have a parent and are not included.
- `GET /sessions/{sid}` returns project, agent name, title, and creation time.
- `PATCH /sessions/{sid}` renames a session with `{"title": "..."}`.
- `DELETE /sessions/{sid}` deletes the session and its data.

## History

`GET /sessions/{sid}/messages` returns the active leaf path, oldest turn first. Each turn includes `id`, `role`, `content`, `parent_id`, `created_at`, optional `context_tokens`, `activity`, and `attachments`.

Do not edit history. To branch or re-run, send a new message with `fork`, `fork_from_turn_id`, or `retry_turn_id` instead.

## Send a message

`POST /sessions/{sid}/messages` accepts:

```json
{
  "content": "List the files in this project.",
  "mode": "agent",
  "skill": null,
  "attachment_ids": [],
  "fork": false,
  "fork_from_turn_id": null,
  "retry_turn_id": null
}
```

- `content` is required.
- `mode` defaults to `agent` and must name a mode defined on the agent.
- `skill` activates one skill for this turn.
- `attachment_ids` references uploads from `POST /sessions/{sid}/attachments` (multipart field `file`).
- `fork: true` with `fork_from_turn_id` branches from that turn.
- `retry_turn_id` re-runs a user turn or the parent of an assistant turn without duplicating the user turn.

The response is `text/event-stream`; see [Streaming](/llms/streaming.md).

## Cancel

`POST /sessions/{sid}/messages/cancel` returns `202` with `{"status": "cancelling"}` when a run is active, or `409` when no run is active.

## Files, plan, and LSP

- `GET /sessions/{sid}/files?q=...` returns `{"files": [...]}` for the project root.
- `GET /sessions/{sid}/plan` returns `{"items": [{"id", "position", "content", "status"}]}`.
- `GET /sessions/{sid}/lsp` returns detected servers, active servers, and diagnostic snapshots.

## Attachments and MCP relay

- `POST /sessions/{sid}/attachments` uploads a file and returns `{id, media_type, filename}`.
- `GET /sessions/{sid}/attachments/{aid}` downloads it.
- `POST /sessions/{sid}/mcp/{server_id}/resources/read` with `{"uri": "..."}` reads an MCP App resource.
- `POST /sessions/{sid}/mcp/{server_id}/tools/call` with `{"name": "...", "arguments": {}}` calls an MCP App tool.

## Subagent sessions

A running agent starts child sessions with its tools: `list_agents`, `start_subagent_session`, `list_subagent_sessions`, `get_subagent_session`, `cancel_subagent_session`, `wait_subagent_session`, and `wait_subagent_sessions`. There is no REST endpoint that creates subagent sessions; use the agent's tools.
