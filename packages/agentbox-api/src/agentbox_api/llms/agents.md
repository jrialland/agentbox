# Agents

An agent is a configuration record, not a running process. It defines the model, instructions, tools, and modes used when a session starts.

## Create an agent

`POST /agents` (permission `agents:create`):

```json
{
  "name": "assistant",
  "description": "Project assistant",
  "instructions": "You are a careful coding assistant.",
  "model": "deepseek-chat",
  "tool_bindings": [{"name": "read_file"}, {"name": "grep"}],
  "mode_definitions": [
    {"name": "ask", "flags": {"write": false}},
    {"name": "agent", "flags": {"write": true}}
  ]
}
```

Fields:

- `name` is required, unique, and cannot be changed by an update.
- `description` and `instructions` are free text. `instructions` is the system prompt and supports prompt templating; preview it with `POST /prompts/preview`.
- Use exactly one of `model` (a model name from `GET /models`) or `model_label` (an assigned label).
- `tool_bindings` selects native tools such as `read_file`, `write_file`, or `grep`, or MCP servers.
- `mode_definitions` defines named modes and their boolean flags; `ask` with `write: false` and `agent` with `write: true` are the usual pair.
- `plugin_mcp_bindings` selects MCP servers contributed by enabled plugins.

Remote MCP binding:

```json
{"server_url": "https://example.com/mcp", "id": "example"}
```

Local stdio MCP binding:

```json
{"id": "filesystem", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]}
```

## Update, read, delete

- `PUT /agents/{name}` (permission `agents:create`) replaces the configuration. The `name` in the body must match the path.
- `GET /agents` and `GET /agents/{name}` require `agents:read`.
- `DELETE /agents/{name}` requires `agents:delete`.

## Avatars and A2A cards

- `GET /agents/{name}/avatar` returns the avatar image; `PUT` uploads one as a multipart field named `file`; `DELETE` restores the generated avatar.
- `GET/PUT/DELETE /agents/{name}/card` manages the A2A agent card. Only agents with a stored card are exposed under `/a2a`.

## Skills

- `GET /skills` and `GET /skills/{name}` list available skills.
- `PUT /skills/{name}` and `DELETE /skills/{name}` manage user skills.
- Activate a skill for one turn with `"skill": "<name>"` in the session message body.
