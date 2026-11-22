# Quickstart

This walkthrough takes an agent from no credentials to a streamed turn. Set the origin and a token first:

```bash
export AGENTBOX_URL=http://localhost:8000
export TOKEN=<jwt or api key>
```

## 1. Authenticate

```bash
curl -sS -X POST "$AGENTBOX_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'
```

Copy `access_token` into `TOKEN`. For a long-lived credential, create an API key as described in [Authentication](/llms/authentication.md).

## 2. Check models

```bash
curl -sS "$AGENTBOX_URL/providers" -H "Authorization: Bearer $TOKEN"
curl -sS "$AGENTBOX_URL/models" -H "Authorization: Bearer $TOKEN"
```

If the model you need is missing, create a provider and refresh or create its models:

```bash
curl -sS -X POST "$AGENTBOX_URL/providers" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "deepseek", "kind": "deepseek", "base_url": "https://api.deepseek.com/v1", "api_key": "<provider key>"}'

curl -sS -X POST "$AGENTBOX_URL/providers/<provider-id>/models/refresh" \
  -H "Authorization: Bearer $TOKEN"
```

A model label such as `smart` can be used instead of a model name if an administrator assigned labels.

## 3. Create a project

`path` must be an existing directory on the server that runs Agentbox.

```bash
curl -sS -X POST "$AGENTBOX_URL/projects" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "demo", "path": "C:\\work\\demo"}'
```

Keep the returned `id` as `PROJECT_ID`.

## 4. Create an agent configuration

Use exactly one of `model` or `model_label`. The `model` value is the model name from `GET /models`, not its id.

```bash
curl -sS -X POST "$AGENTBOX_URL/agents" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "assistant",
    "description": "Project assistant",
    "instructions": "You are a careful coding assistant.",
    "model": "deepseek-chat",
    "tool_bindings": [{"name": "read_file"}, {"name": "write_file"}],
    "mode_definitions": [
      {"name": "ask", "flags": {"write": false}},
      {"name": "agent", "flags": {"write": true}}
    ]
  }'
```

## 5. Create a session

The request field is named `agent_id`, but its value is the agent configuration **name**.

```bash
curl -sS -X POST "$AGENTBOX_URL/sessions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project_id": "<project-id>", "agent_id": "assistant"}'
```

Keep the returned `id` as `SESSION_ID`.

## 6. Send a message and consume the stream

```bash
curl -N -X POST "$AGENTBOX_URL/sessions/$SESSION_ID/messages" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"content": "List the files in this project.", "mode": "agent"}'
```

The response is an AG-UI server-sent-event stream. Keep reading until `RUN_FINISHED` or `RUN_ERROR`; see [Streaming](/llms/streaming.md).

## 7. Read history

```bash
curl -sS "$AGENTBOX_URL/sessions/$SESSION_ID/messages" \
  -H "Authorization: Bearer $TOKEN"
```

The response is the active conversation leaf, oldest turn first.
